# Host-only audit of the unchanged 2017.4 reference in a disposable build copy.
# Usage: vivado -mode batch -source this.tcl -tclargs hls|hls-repack|bd
set project_root [file normalize [file join [file dirname [info script]] ..]]
set work_base [file join $project_root build official_v2.2.1 boards Pynq-Z2 base]
set results [file join $project_root results audit official_v2.2.1]
file mkdir $results
set_param board.repoPaths [list [file join $project_root references board pynq-z2 pynq-z2]]
cd $work_base
set stage [lindex $argv 0]
if {$stage eq "hls"} {
    if {[catch {source build_base_ip.tcl} reason opts]} {
        puts stderr "OFFICIAL_HLS_FAILED: $reason"
        puts stderr [dict get $opts -errorinfo]
        exit 1
    }
    puts "OFFICIAL_HLS_COMPLETE"
} elseif {$stage eq "hls-repack"} {
    # Project-local workaround ONLY for generated packaging metadata. The
    # failed stock attempt stays in hls.log; original HLS scripts/C++ and the
    # installed tool are untouched. This is not an installed AMD patch.
    cd ../../ip/hls
    foreach item {color_convert pixel_pack pixel_unpack trace_cntrl_32 trace_cntrl_64} {
        set initial [open [file join $results ${item}_stock_export.log] w]
        set failed [catch {exec vivado_hls -f $item/script.tcl 2>@1} output]
        puts $initial $output
        close $initial
        set ipdir [file normalize [file join $item solution1 impl ip]]
        set packaging [file join $ipdir run_ippack.tcl]
        if {![file exists $packaging]} {error "No packaging script for $item; synthesis failed"}
        set fp [open $packaging r]
        set generated [read $fp]
        close $fp
        if {$failed && ![string match "*bad lexical cast*" $output]} {
            error "Unexpected failure in $item; see stock_export.log"
        }
        if {$failed} {
            set count [regsub -all -line {^set Revision[ \t]+"[0-9]+"} $generated {set Revision "1"} patched]
            if {$count != 1} {error "Unexpected generated revision metadata"}
            set fp [open [file join $ipdir run_ippack_audit.tcl] w]
            puts -nonewline $fp $patched
            close $fp
            set previous [pwd]
            cd $ipdir
            set repack_failed [catch {exec vivado -mode batch -nojournal -log [file join $results ${item}_repack.log] -source run_ippack_audit.tcl 2>@1} repack_output]
            cd $previous
            if {$repack_failed} {error "Metadata repack failed for $item: $repack_output"}
            puts "METADATA_REPACK_COMPLETE: $item, core_revision=1; original RTL unchanged"
        }
        if {[llength [glob -nocomplain -directory $ipdir *.zip]] == 0} {error "Missing packaged $item"}
        file copy -force [file join $item solution1 syn report ${item}_csynth.rpt] [file join $results ${item}_csynth.rpt]
        file copy -force $packaging [file join $results ${item}_run_ippack_original.tcl]
        if {$failed} {
            file copy -force [file join $ipdir run_ippack_audit.tcl] [file join $results ${item}_run_ippack_audit.tcl]
        }
    }
    puts "OFFICIAL_HLS_REPACK_COMPLETE: stock export failed; local metadata workaround verified"
} elseif {$stage eq "bd"} {
    # Stop at the stock script's explicit implementation boundary. No RTL,
    # IP parameters, clocks, addresses, XDC or version check are changed.
    set fp [open base.tcl r]
    set source_text [read $fp]
    close $fp
    set boundary [string first "# Additional steps to get to bitstream" $source_text]
    if {$boundary < 0} {error "Expected upstream boundary missing"}
    if {[catch {uplevel #0 [string range $source_text 0 [expr {$boundary-1}]]} reason opts]} {
        puts stderr "OFFICIAL_BD_FAILED: $reason"
        puts stderr [dict get $opts -errorinfo]
        exit 1
    }
    if {[llength [get_bd_cells -quiet ps7_0]] != 1} {error "Stock reference was not created"}
    validate_bd_design
    save_bd_design
    write_bd_tcl -force [file join $results reconstructed_bd.tcl]
    report_ip_status -file [file join $results ip_status.rpt]
    set inventory [open [file join $results ip_inventory.tsv] w]
    puts $inventory "instance\tvlnv\tinterfaces\tclock_pins"
    foreach cell [lsort [get_bd_cells -hier -filter {TYPE == ip}]] {
        set clocks [get_bd_pins -quiet -of_objects $cell -filter {TYPE == clk}]
        puts $inventory "$cell\t[get_property VLNV $cell]\t[get_bd_intf_pins -quiet -of_objects $cell]\t$clocks"
    }
    close $inventory
    puts "OFFICIAL_BD_VALIDATED: host-only, no bitstream or board verification"
} else {
    error "Choose hls, hls-repack or bd"
}
exit 0
