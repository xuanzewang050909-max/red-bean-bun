// Frozen Q1 candidate C2_l9_d12345_m1_p28.
// Reuse the installed, unmodified 2017.4 filter_opr/Window/LineBuffer.
// Only the medical window operation and aligned response join are new.
#include "retina_c2_support_hls.hpp"

template<int DY,int DX,int SHIFT,typename T>
static ap_uint<12> c2_line_sum(hls::Window<19,19,T>& pixels) {
#pragma HLS INLINE
    ap_uint<12> samples[9];
#pragma HLS ARRAY_PARTITION variable=samples complete
    for(int index=0;index<9;++index) {
#pragma HLS UNROLL
        const int t=index-4;
        // Vendor window rows and columns run opposite the image axes.
        samples[index]=pixels.val[9-(t*DY-SHIFT*DX)][9-(t*DX+SHIFT*DY)];
    }
    // All intermediates fit 12 unsigned bits: a nine-pixel sum <=2295.
    ap_uint<12> a=samples[0]+samples[1];
    ap_uint<12> b=samples[2]+samples[3];
    ap_uint<12> c=samples[4]+samples[5];
    ap_uint<12> d=samples[6]+samples[7];
    return ((a+b)+(c+d))+samples[8];
}

template<int DY,int DX,int DISTANCE,typename T>
static ap_uint<1> c2_pair(hls::Window<19,19,T>& pixels,ap_uint<12> center) {
#pragma HLS INLINE
    ap_uint<12> left=c2_line_sum<DY,DX,-DISTANCE>(pixels);
    ap_uint<12> right=c2_line_sum<DY,DX,DISTANCE>(pixels);
    // Signed widening occurs before subtraction; retain negative evidence.
    ap_int<13> dl=ap_int<13>(left)-ap_int<13>(center);
    ap_int<13> dr=ap_int<13>(right)-ap_int<13>(center);
    return (dl>=9)&&(dr>=9);
}

template<int DY,int DX,typename T>
static ap_uint<1> c2_direction(hls::Window<19,19,T>& pixels) {
#pragma HLS INLINE
    ap_uint<12> center=c2_line_sum<DY,DX,0>(pixels);
    return c2_pair<DY,DX,1>(pixels,center)|c2_pair<DY,DX,2>(pixels,center)|
           c2_pair<DY,DX,3>(pixels,center)|c2_pair<DY,DX,4>(pixels,center)|
           c2_pair<DY,DX,5>(pixels,center);
}

class C2SupportKernel {
public:
    template<typename SRC_T,typename DST_T,typename FILTER_T,int H,int W>
    void apply(hls::Window<H,W,FILTER_T>& kernel,
               hls::Window<H,W,SRC_T>& pixels,DST_T& output) {
#pragma HLS INLINE
        // The dummy coefficient window is part of the vendor filter interface.
        // All four directions share one replicated-border pixel window.
        output=c2_direction<0,1>(pixels)|c2_direction<1,0>(pixels)|
               c2_direction<1,1>(pixels)|c2_direction<1,-1>(pixels);
    }
};

void retina_c2_support(C2Image& enhanced,C2Image& supported) {
#pragma HLS INLINE off
    hls::Window<19,19,ap_uint<1> > kernel;
    for(int y=0;y<19;++y)for(int x=0;x<19;++x) {
#pragma HLS UNROLL
        kernel.val[y][x]=0;
    }
    hls::Point_<int> anchor(9,9);
    hls::filter_opr<C2SupportKernel,hls::BORDER_REPLICATE>::filter(
        enhanced,supported,kernel,anchor,enhanced.rows,enhanced.cols);
}

static void c2_split(hls::stream<ap_uint<32> >& source,C2Image& enhanced,
                     hls::stream<ap_uint<32> >& aligned,int count) {
    for(int i=0;i<count;++i) {
#pragma HLS PIPELINE II=1
        ap_uint<32> word=source.read();
        hls::Scalar<1,unsigned char> value;
        value.val[0]=word.range(7,0);
        enhanced.write(value);
        aligned.write(word);
    }
}

static void c2_join(C2Image& supported,hls::stream<ap_uint<32> >& aligned,
                    hls::stream<ap_uint<32> >& result,int count) {
    for(int i=0;i<count;++i) {
#pragma HLS PIPELINE II=1
        hls::Scalar<1,unsigned char> value=supported.read();
        ap_uint<32> word=aligned.read();
        ap_uint<8> response=word.range(15,8);
        ap_uint<1> accept=(value.val[0]!=0);
        ap_uint<8> softened=accept ? response :
            response>=28 ? ap_uint<8>(response-28) : ap_uint<8>(0);
        ap_uint<32> output=word;
        output.range(7,0)=softened;
        output.range(15,8)=accept ? 1 : 0;
        result.write(output);
    }
}

void retina_c2_support_hls(hls::stream<ap_uint<32> >& source,
                           hls::stream<ap_uint<32> >& result,ap_uint<32> side) {
#pragma HLS INTERFACE axis port=source
#pragma HLS INTERFACE axis port=result
#pragma HLS INTERFACE ap_none port=side
#pragma HLS INTERFACE ap_ctrl_hs port=return
#pragma HLS DATAFLOW
    int size=side;
    int count=size*size;
    C2Image enhanced(size,size),supported(size,size);
    hls::stream<ap_uint<32> > aligned;
#pragma HLS STREAM variable=aligned depth=8192
#pragma HLS RESOURCE variable=aligned core=FIFO_BRAM
#pragma HLS STREAM variable=enhanced.data_stream depth=32
#pragma HLS STREAM variable=supported.data_stream depth=32
    c2_split(source,enhanced,aligned,count);
    retina_c2_support(enhanced,supported);
    c2_join(supported,aligned,result,count);
}
