// A3 derives the verified A2 Gaussian stage and reuses vendor BoxFilter.
// Installed HLS headers, line buffers and frame guard are not modified.
#include "retina_background_hls.hpp"

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

static void join_words(SumImage& sums, hls::stream<ap_uint<32> >& centers,
                       hls::stream<ap_uint<8> >& enhanced_centers,
                       hls::stream<ap_uint<32> >& result, int count, ap_uint<2> mode) {
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
        ap_uint<32> output=0;
        output.range(7,0)=word.range(15,8);
        output.range(15,8)=enhanced;
        output.range(23,16)=mode==1 ? ap_uint<8>(0) : background;
        output.range(31,24)=mode==3 ? response : ap_uint<8>(word.range(31,24));
        result.write(mode==0 ? word : output);
    }
}

// A separate aligned enhanced stream avoids recomputing Gaussian on the PS.
static void enhance_aligned(SumImage& sums, hls::stream<ap_uint<32> >& original,
                            GreenImage& enhanced, hls::stream<ap_uint<32> >& centers,
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
        centers.write(word);
        enhanced_centers.write(ap_uint<8>(value.val[0]));
    }
}

void retina_background_hls(hls::stream<ap_uint<32> >& source,
                           hls::stream<ap_uint<32> >& result, ap_uint<32> control) {
#pragma HLS INTERFACE axis port=source
#pragma HLS INTERFACE axis port=result
#pragma HLS INTERFACE ap_none port=control
#pragma HLS INTERFACE ap_ctrl_hs port=return
#pragma HLS DATAFLOW
    int side=control[2] ? 256 : 512;
    int count=side*side;
    GreenImage green(side,side),enhanced(side,side);
    SumImage gaussian_sums(side,side),box_sums(side,side);
    hls::stream<ap_uint<32> > original,centers;
    hls::stream<ap_uint<8> > enhanced_centers;
#pragma HLS STREAM variable=original depth=2048
#pragma HLS RESOURCE variable=original core=FIFO_BRAM
#pragma HLS STREAM variable=centers depth=8192
#pragma HLS RESOURCE variable=centers core=FIFO_BRAM
#pragma HLS STREAM variable=enhanced_centers depth=8192
#pragma HLS RESOURCE variable=enhanced_centers core=FIFO_BRAM
#pragma HLS STREAM variable=green.data_stream depth=32
#pragma HLS STREAM variable=gaussian_sums.data_stream depth=32
#pragma HLS STREAM variable=enhanced.data_stream depth=32
#pragma HLS STREAM variable=box_sums.data_stream depth=32
    split_words(source,green,original,count);
    filter_sum(green,gaussian_sums);
    enhance_aligned(gaussian_sums,original,enhanced,centers,enhanced_centers,count);
    background_sum(enhanced,box_sums);
    join_words(box_sums,centers,enhanced_centers,result,count,control.range(1,0));
}
