// Reuse installed Vivado HLS 2017.4 Filter2D/LineBuffer/BORDER_REPLICATE.
// No vendor library headers are copied into this repository.
#include "retina_gaussian_hls.hpp"

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
    // Unscaled integers: exact accumulation into uint16; round once afterwards.
    const unsigned char weights[3][3]={{1,2,1},{2,4,2},{1,2,1}};
    for(int y=0;y<3;++y) for(int x=0;x<3;++x) {
#pragma HLS UNROLL
        kernel.val[y][x]=weights[y][x];
    }
    hls::Point_<int> anchor(1,1);
    hls::Filter2D<hls::BORDER_REPLICATE>(green,sums,kernel,anchor);
}

static void join_words(SumImage& sums, hls::stream<ap_uint<32> >& original,
                       hls::stream<ap_uint<32> >& result, int count, ap_uint<2> mode) {
    for(int i=0;i<count;++i) {
#pragma HLS PIPELINE II=1
        hls::Scalar<1,unsigned short> pixel=sums.read();
        ap_uint<32> word=original.read();
        ap_uint<12> total=pixel.val[0];
        ap_uint<8> gaussian=(total+ap_uint<12>(8)) >> 4;
        // Fixed table enables an exact LUT instead of a general divider.
        static const unsigned char lut[256]={
#include "contrast_lut_values.h"
        };
        ap_uint<8> value=(mode==1) ? ap_uint<8>(word.range(15,8)) :
                           (mode==2) ? gaussian : ap_uint<8>(lut[gaussian]);
        ap_uint<32> output=0;
        output.range(7,0)=word.range(15,8);
        output.range(15,8)=value;
        output.range(31,24)=word.range(31,24); // Center FOV delayed with raw G.
        result.write(mode==0 ? word : output);
    }
}

void retina_gaussian_hls(hls::stream<ap_uint<32> >& source,
                         hls::stream<ap_uint<32> >& result, ap_uint<32> control) {
#pragma HLS INTERFACE axis port=source
#pragma HLS INTERFACE axis port=result
#pragma HLS INTERFACE ap_none port=control
#pragma HLS INTERFACE ap_ctrl_hs port=return
#pragma HLS DATAFLOW
    int side=control[2] ? 256 : 512;
    int count=side*side;
    GreenImage green(side,side);
    SumImage sums(side,side);
    hls::stream<ap_uint<32> > original;
#pragma HLS STREAM variable=original depth=2048
#pragma HLS RESOURCE variable=original core=FIFO_BRAM
#pragma HLS STREAM variable=green.data_stream depth=32
#pragma HLS STREAM variable=sums.data_stream depth=32
    split_words(source,green,original,count);
    filter_sum(green,sums);
    join_words(sums,original,result,count,control.range(1,0));
}
