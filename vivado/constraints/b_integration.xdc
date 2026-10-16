# Derived exclusively from pinned PYNQ-Z2 v2.2.1 top.xdc.
# GPIO/HDMI pin assignments unchanged; audio/IOP removed with their BD groups.
# RX period retains the nominal 120 MHz with adequate precision (600 MHz VCO).

 #  Copyright (c) 2016, Xilinx, Inc.
 #  All rights reserved.
 #
 #  Redistribution and use in source and binary forms, with or without
 #  modification, are permitted provided that the following conditions are met:
 #
 #  1.  Redistributions of source code must retain the above copyright notice,
 #     this list of conditions and the following disclaimer.
 #
 #  2.  Redistributions in binary form must reproduce the above copyright
 #      notice, this list of conditions and the following disclaimer in the
 #      documentation and/or other materials provided with the distribution.
 #
 #  3.  Neither the name of the copyright holder nor the names of its
 #      contributors may be used to endorse or promote products derived from
 #      this software without specific prior written permission.
 #
 #  THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
 #  AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO,
 #  THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR
 #  PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR
 #  CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL,
 #  EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO,
 #  PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS;
 #  OR BUSINESS INTERRUPTION). HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY,
 #  WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR
 #  OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF
 #  ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
 #

## Switches
set_property -dict {PACKAGE_PIN M20 IOSTANDARD LVCMOS33} [get_ports {sws_2bits_tri_i[0]}]
set_property -dict {PACKAGE_PIN M19 IOSTANDARD LVCMOS33} [get_ports {sws_2bits_tri_i[1]}]

## Buttons
set_property -dict {PACKAGE_PIN D19 IOSTANDARD LVCMOS33} [get_ports {btns_4bits_tri_i[0]}]
set_property -dict {PACKAGE_PIN D20 IOSTANDARD LVCMOS33} [get_ports {btns_4bits_tri_i[1]}]
set_property -dict {PACKAGE_PIN L20 IOSTANDARD LVCMOS33} [get_ports {btns_4bits_tri_i[2]}]
set_property -dict {PACKAGE_PIN L19 IOSTANDARD LVCMOS33} [get_ports {btns_4bits_tri_i[3]}]

## LEDs
set_property -dict {PACKAGE_PIN R14 IOSTANDARD LVCMOS33} [get_ports {leds_4bits_tri_o[0]}]
set_property -dict {PACKAGE_PIN P14 IOSTANDARD LVCMOS33} [get_ports {leds_4bits_tri_o[1]}]
set_property -dict {PACKAGE_PIN N16 IOSTANDARD LVCMOS33} [get_ports {leds_4bits_tri_o[2]}]
set_property -dict {PACKAGE_PIN M14 IOSTANDARD LVCMOS33} [get_ports {leds_4bits_tri_o[3]}]

## RGBLEDs
set_property -dict { PACKAGE_PIN L15   IOSTANDARD LVCMOS33 } [get_ports { rgbleds_6bits_tri_o[0] }]; 
set_property -dict { PACKAGE_PIN G17   IOSTANDARD LVCMOS33 } [get_ports { rgbleds_6bits_tri_o[1] }]; 
set_property -dict { PACKAGE_PIN N15   IOSTANDARD LVCMOS33 } [get_ports { rgbleds_6bits_tri_o[2] }]; 
set_property -dict { PACKAGE_PIN G14   IOSTANDARD LVCMOS33 } [get_ports { rgbleds_6bits_tri_o[3] }];
set_property -dict { PACKAGE_PIN L14   IOSTANDARD LVCMOS33 } [get_ports { rgbleds_6bits_tri_o[4] }]; 
set_property -dict { PACKAGE_PIN M15   IOSTANDARD LVCMOS33 } [get_ports { rgbleds_6bits_tri_o[5] }]; 

#HDMI Signals
create_clock -period 8.333333 -waveform {0.000 4.1666665} [get_ports hdmi_in_clk_p]
# create_clock -period 6.900 -name output_video -waveform {0.000 3.450} [get_pins system_i/video/hdmi_out/frontend/axi_dynclk/PXL_CLK_O]

# Following pins are for HDMI RX on Rev B board
set_property -dict {PACKAGE_PIN P19 IOSTANDARD TMDS_33} [get_ports hdmi_in_clk_n]
set_property -dict {PACKAGE_PIN N18 IOSTANDARD TMDS_33} [get_ports hdmi_in_clk_p]
set_property -dict {PACKAGE_PIN W20 IOSTANDARD TMDS_33} [get_ports {hdmi_in_data_n[0]}]
set_property -dict {PACKAGE_PIN V20 IOSTANDARD TMDS_33} [get_ports {hdmi_in_data_p[0]}]
set_property -dict {PACKAGE_PIN U20 IOSTANDARD TMDS_33} [get_ports {hdmi_in_data_n[1]}]
set_property -dict {PACKAGE_PIN T20 IOSTANDARD TMDS_33} [get_ports {hdmi_in_data_p[1]}]
set_property -dict {PACKAGE_PIN P20 IOSTANDARD TMDS_33} [get_ports {hdmi_in_data_n[2]}]
set_property -dict {PACKAGE_PIN N20 IOSTANDARD TMDS_33} [get_ports {hdmi_in_data_p[2]}]
set_property -dict {PACKAGE_PIN T19 IOSTANDARD LVCMOS33} [get_ports {hdmi_in_hpd[0]}]
set_property -dict {PACKAGE_PIN U14 IOSTANDARD LVCMOS33} [get_ports hdmi_in_ddc_scl_io]
set_property -dict {PACKAGE_PIN U15 IOSTANDARD LVCMOS33} [get_ports hdmi_in_ddc_sda_io]

# Following pins are for HDMI TX on Rev B board
set_property -dict {PACKAGE_PIN L17 IOSTANDARD TMDS_33} [get_ports hdmi_out_clk_n]
set_property -dict {PACKAGE_PIN L16 IOSTANDARD TMDS_33} [get_ports hdmi_out_clk_p]
set_property -dict {PACKAGE_PIN K18 IOSTANDARD TMDS_33} [get_ports {hdmi_out_data_n[0]}]
set_property -dict {PACKAGE_PIN K17 IOSTANDARD TMDS_33} [get_ports {hdmi_out_data_p[0]}]
set_property -dict {PACKAGE_PIN J19 IOSTANDARD TMDS_33} [get_ports {hdmi_out_data_n[1]}]
set_property -dict {PACKAGE_PIN K19 IOSTANDARD TMDS_33} [get_ports {hdmi_out_data_p[1]}]
set_property -dict {PACKAGE_PIN H18 IOSTANDARD TMDS_33} [get_ports {hdmi_out_data_n[2]}]
set_property -dict {PACKAGE_PIN J18 IOSTANDARD TMDS_33} [get_ports {hdmi_out_data_p[2]}]
set_property -dict {PACKAGE_PIN R19 IOSTANDARD LVCMOS33} [get_ports {hdmi_out_hpd[0]}]

