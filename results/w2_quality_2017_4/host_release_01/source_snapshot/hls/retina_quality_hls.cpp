// Q2 WORKING PIPELINE: derived from the immutable board-verified A4.
// C2 support and dynamic threshold are not yet a paired production overlay.
#include "retina_quality_hls.hpp"

typedef hls::Mat<512,512,HLS_8UC1> GreenImage;
typedef hls::Mat<512,512,HLS_16UC1> SumImage;

static void split_words(hls::stream<ap_uint<32> >& source, GreenImage& green,
                        hls::stream<ap_uint<32> >& original, int count) {
    for (int i=0; i<count; ++i) {
#pragma HLS PIPELINE II=1
        ap_uint<32> word=source.read();
        hls::Scalar<1,unsigned char> pixel;
        pixel.val[0]=word.range(15,8);
        green.write(pixel);
        original.write(word);
    }
}

static void filter_sum(GreenImage& green, SumImage& sums) {
    hls::Window<3,3,ap_uint<4> > kernel;
    const unsigned char weights[3][3]={{1,2,1},{2,4,2},{1,2,1}};
    for(int y=0;y<3;++y) for(int x=0;x<3;++x) {
#pragma HLS UNROLL
        kernel.val[y][x]=weights[y][x];
    }
    hls::Point_<int> anchor(1,1);
    hls::Filter2D<hls::BORDER_REPLICATE>(green,sums,kernel,anchor);
}

static void background_sum(GreenImage& enhanced, SumImage& sums) {
    // NORMALIZE=false avoids a quantized reciprocal and intermediate rounding.
    hls::BoxFilter<15,15,false,hls::BORDER_REPLICATE>(enhanced,sums,hls::Point_<int>(7,7));
}

static void response_carrier(SumImage& sums, hls::stream<ap_uint<32> >& centers,
                             hls::stream<ap_uint<8> >& enhanced_centers,
                             hls::stream<ap_uint<64> >& aligned,
                             int count) {
    for(int i=0;i<count;++i) {
#pragma HLS PIPELINE II=1
        hls::Scalar<1,unsigned short> pixel=sums.read();
        ap_uint<32> word=centers.read();
        ap_uint<8> enhanced=enhanced_centers.read();
        ap_uint<16> sum=pixel.val[0];
        ap_uint<8> background=(sum+ap_uint<16>(112))/ap_uint<16>(225);
        ap_int<10> difference=ap_int<10>(background)-ap_int<10>(enhanced);
        ap_uint<8> response=difference<=0 ? ap_uint<8>(0) :
                            difference>=64 ? ap_uint<8>(255) : ap_uint<8>(difference*4);
        ap_uint<64> carrier=0;
        carrier.range(31,0)=word;
        carrier.range(39,32)=enhanced;
        carrier.range(47,40)=response;
        aligned.write(carrier);
    }
}

// A separate aligned enhanced stream avoids recomputing Gaussian on the PS.
static void enhance_aligned(SumImage& sums, hls::stream<ap_uint<32> >& original,
                            GreenImage& enhanced, GreenImage& support_input, hls::stream<ap_uint<32> >& centers,
                            hls::stream<ap_uint<8> >& enhanced_centers, int count) {
    for(int i=0;i<count;++i) {
#pragma HLS PIPELINE II=1
        hls::Scalar<1,unsigned short> pixel=sums.read();
        ap_uint<32> word=original.read();
        ap_uint<12> total=pixel.val[0];
        ap_uint<8> gaussian=(total+ap_uint<12>(8)) >> 4;
        static const unsigned char lut[256]={
#include "contrast_lut_values.h"
        };
        hls::Scalar<1,unsigned char> value;
        value.val[0]=lut[gaussian];
        enhanced.write(value);
        support_input.write(value);
        centers.write(word);
        enhanced_centers.write(ap_uint<8>(value.val[0]));
    }
}

static void select_response(GreenImage& support,
                             hls::stream<ap_uint<64> >& original,
                             GreenImage& responses,hls::stream<ap_uint<64> >& selected,
                             int count,ap_uint<1> use_c2) {
    for(int i=0;i<count;++i) {
#pragma HLS PIPELINE II=1
        hls::Scalar<1,unsigned char> evidence=support.read();
        ap_uint<64> carrier=original.read();
        ap_uint<8> response=carrier.range(47,40);
        if(use_c2 && !evidence.val[0])
            response=response>=28 ? ap_uint<8>(response-28) : ap_uint<8>(0);
        carrier.range(47,40)=response;
        hls::Scalar<1,unsigned char> value;
        value.val[0]=response;
        responses.write(value);
        selected.write(carrier);
    }
}

static void threshold_binary(GreenImage& responses,GreenImage& binary,ap_uint<8> threshold) {
    // Working ABI requires threshold 1..255. W2 must reject zero before START.
    hls::Threshold(responses,binary,(unsigned char)(threshold-1),(unsigned char)1,HLS_THRESH_BINARY);
}

static void initial_fov(GreenImage& binary, hls::stream<ap_uint<64> >& aligned,
                        GreenImage& initial, hls::stream<ap_uint<64> >& delayed, int count) {
    for(int i=0;i<count;++i) {
#pragma HLS PIPELINE II=1
        hls::Scalar<1,unsigned char> value=binary.read();
        ap_uint<64> carrier=aligned.read();
        ap_uint<1> mask=(value.val[0]!=0) && carrier[24];
        carrier[48]=mask;
        value.val[0]=mask;
        initial.write(value);
        delayed.write(carrier);
    }
}

static void dilate_zero(GreenImage& input, GreenImage& output) {
    hls::Window<3,3,unsigned char> cross;
    const unsigned char values[3][3]={{0,1,0},{1,1,1},{0,1,0}};
    for(int y=0;y<3;++y) for(int x=0;x<3;++x) {
#pragma HLS UNROLL
        cross.val[y][x]=values[y][x];
    }
    hls::morp_opr<hls::dilate_kernel,hls::BORDER_CONSTANT,hls::MORPH_CROSS,1>(
        input,output,cross,hls::Point_<int>(1,1));
}

static void erode_zero(GreenImage& input, GreenImage& output) {
    hls::Window<3,3,unsigned char> cross;
    const unsigned char values[3][3]={{0,1,0},{1,1,1},{0,1,0}};
    for(int y=0;y<3;++y) for(int x=0;x<3;++x) {
#pragma HLS UNROLL
        cross.val[y][x]=values[y][x];
    }
    hls::morp_opr<hls::erode_kernel,hls::BORDER_CONSTANT,hls::MORPH_CROSS,1>(
        input,output,cross,hls::Point_<int>(1,1));
}

static void closed_carrier(GreenImage& closed, hls::stream<ap_uint<64> >& aligned,
                           GreenImage& count_input, hls::stream<ap_uint<64> >& delayed, int count) {
    for(int i=0;i<count;++i) {
#pragma HLS PIPELINE II=1
        hls::Scalar<1,unsigned char> value=closed.read();
        ap_uint<64> carrier=aligned.read();
        carrier[49]=(value.val[0]!=0);
        count_input.write(value);
        delayed.write(carrier);
    }
}

static void count_neighbors(GreenImage& input, GreenImage& output) {
    hls::Window<3,3,ap_uint<1> > ones;
    for(int y=0;y<3;++y) for(int x=0;x<3;++x) {
#pragma HLS UNROLL
        ones.val[y][x]=1;
    }
    hls::Filter2D<hls::BORDER_REPLICATE>(input,output,ones,hls::Point_<int>(1,1));
}

static void final_join(GreenImage& counts, hls::stream<ap_uint<64> >& aligned,
                       hls::stream<ap_uint<32> >& result, int count, ap_uint<2> mode) {
    for(int i=0;i<count;++i) {
#pragma HLS PIPELINE II=1
        hls::Scalar<1,unsigned char> neighbours=counts.read();
        ap_uint<64> carrier=aligned.read();
        ap_uint<1> final_mask=carrier[49] && (neighbours.val[0]>=2) && carrier[24];
        ap_uint<1> selected=mode==1 ? ap_uint<1>(carrier[48]) :
                             mode==2 ? ap_uint<1>(carrier[49]) : final_mask;
        ap_uint<32> output=0;
        output.range(7,0)=carrier.range(15,8);
        output.range(15,8)=carrier.range(39,32);
        output.range(23,16)=selected ? 255 : 0;
        output.range(31,24)=carrier.range(47,40);
        result.write(mode==0 ? ap_uint<32>(carrier.range(31,0)) : output);
    }
}

void retina_quality_hls(hls::stream<ap_uint<32> >& source,
                             hls::stream<ap_uint<32> >& result, ap_uint<32> control) {
#pragma HLS INTERFACE axis port=source
#pragma HLS INTERFACE axis port=result
#pragma HLS INTERFACE ap_none port=control
#pragma HLS INTERFACE ap_ctrl_hs port=return
#pragma HLS DATAFLOW
    int side=control[2] ? 256 : 512;
    int count=side*side;
    GreenImage green(side,side),enhanced(side,side),responses(side,side),binary(side,side);
    GreenImage support_input(side,side),support(side,side);
    GreenImage initial(side,side),dilated(side,side),closed(side,side),count_input(side,side),counts(side,side);
    SumImage gaussian_sums(side,side),box_sums(side,side);
    hls::stream<ap_uint<32> > original,centers;
    hls::stream<ap_uint<8> > enhanced_centers;
    hls::stream<ap_uint<64> > original_response,aligned_response,aligned_initial,aligned_closed;
#pragma HLS STREAM variable=original_response depth=8192
#pragma HLS RESOURCE variable=original_response core=FIFO_BRAM
#pragma HLS STREAM variable=support_input.data_stream depth=32
#pragma HLS STREAM variable=support.data_stream depth=32
#pragma HLS STREAM variable=original depth=2048
#pragma HLS RESOURCE variable=original core=FIFO_BRAM
#pragma HLS STREAM variable=centers depth=8192
#pragma HLS RESOURCE variable=centers core=FIFO_BRAM
#pragma HLS STREAM variable=enhanced_centers depth=8192
#pragma HLS RESOURCE variable=enhanced_centers core=FIFO_BRAM
#pragma HLS STREAM variable=aligned_response depth=32
#pragma HLS STREAM variable=aligned_initial depth=2048
#pragma HLS RESOURCE variable=aligned_initial core=FIFO_BRAM
#pragma HLS STREAM variable=aligned_closed depth=2048
#pragma HLS RESOURCE variable=aligned_closed core=FIFO_BRAM
#pragma HLS STREAM variable=green.data_stream depth=32
#pragma HLS STREAM variable=gaussian_sums.data_stream depth=32
#pragma HLS STREAM variable=enhanced.data_stream depth=32
#pragma HLS STREAM variable=box_sums.data_stream depth=32
#pragma HLS STREAM variable=responses.data_stream depth=32
#pragma HLS STREAM variable=binary.data_stream depth=32
#pragma HLS STREAM variable=initial.data_stream depth=32
#pragma HLS STREAM variable=dilated.data_stream depth=32
#pragma HLS STREAM variable=closed.data_stream depth=32
#pragma HLS STREAM variable=count_input.data_stream depth=32
#pragma HLS STREAM variable=counts.data_stream depth=32
    split_words(source,green,original,count);
    filter_sum(green,gaussian_sums);
    enhance_aligned(gaussian_sums,original,enhanced,support_input,centers,enhanced_centers,count);
    background_sum(enhanced,box_sums);
    response_carrier(box_sums,centers,enhanced_centers,original_response,count);
    retina_c2_support(support_input,support);
    select_response(support,original_response,responses,aligned_response,count,control[3]);
    threshold_binary(responses,binary,control.range(15,8));
    initial_fov(binary,aligned_response,initial,aligned_initial,count);
    dilate_zero(initial,dilated);
    erode_zero(dilated,closed);
    closed_carrier(closed,aligned_initial,count_input,aligned_closed,count);
    count_neighbors(count_input,counts);
    final_join(counts,aligned_closed,result,count,control.range(1,0));
}
