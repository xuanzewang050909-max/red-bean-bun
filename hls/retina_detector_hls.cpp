// C7 fixed image-only 36-feature / 8-tree classifier. All computations in PL.
// Vendor 2017.4 filter_opr supplies the unmodified replicated-border window.
#include "retina_detector_hls.hpp"
#include "retina_c7_model.hpp"
typedef hls::Mat<512,512,HLS_16UC1> C7Plane;

template<int DY,int DX,typename T>
static ap_uint<8> c7_at(hls::Window<17,17,T>& p) {
#pragma HLS INLINE
    return ap_uint<8>(p.val[8-DY][8-DX]);
}

// Balanced, exact reductions avoid a 225-comparison serial min/max chain.
// Maximum sum is 225*255=57375, so 16 bits are sufficient at every node.
template<int N,int START,int COUNT> struct C7Reduce {
    template<typename T>
    static void run(hls::Window<17,17,T>& p,ap_uint<16>& sum,ap_uint<8>& low,ap_uint<8>& high) {
#pragma HLS INLINE
        ap_uint<16> sa,sb;ap_uint<8> la,lb,ha,hb;
        C7Reduce<N,START,COUNT/2>::run(p,sa,la,ha);
        C7Reduce<N,START+COUNT/2,COUNT-COUNT/2>::run(p,sb,lb,hb);
        sum=sa+sb;low=la<lb?la:lb;high=ha>hb?ha:hb;
    }
};
template<int N,int START> struct C7Reduce<N,START,1> {
    template<typename T>
    static void run(hls::Window<17,17,T>& p,ap_uint<16>& sum,ap_uint<8>& low,ap_uint<8>& high) {
#pragma HLS INLINE
        ap_uint<8> v=p.val[8-N/2+START/N][8-N/2+START%N];
        sum=v;low=v;high=v;
    }
};

template<int N,typename T>
static ap_uint<8> c7_mean(hls::Window<17,17,T>& p) {
#pragma HLS INLINE
    ap_uint<16> sum;ap_uint<8> low,high;
    C7Reduce<N,0,N*N>::run(p,sum,low,high);
    return (sum+N*N/2)/(N*N);
}

template<int L>
static ap_int<10> c7_round(ap_int<14> value) {
#pragma HLS INLINE
    // Odd divisors have no exact half-tie; C++ signed division truncates to zero.
    return value>=0 ? ap_int<10>((value+L/2)/L) : ap_int<10>(-((-value+L/2)/L));
}

template<int L,int DY,int DX,int DIST,typename T>
static ap_uint<12> c7_line(hls::Window<17,17,T>& p) {
#pragma HLS INLINE
    ap_uint<12> total=0;
    for(int i=0;i<L;++i) {
#pragma HLS UNROLL
        int t=i-L/2;
        total+=ap_uint<8>(p.val[8-(t*DY-DIST*DX)][8-(t*DX+DIST*DY)]);
    }
    return total;
}

template<int L,int DY,int DX,int DIST,typename T>
static void c7_pair(hls::Window<17,17,T>& p,ap_int<14>& small,ap_uint<13>& imbalance,ap_int<10>& central) {
#pragma HLS INLINE
    ap_int<14> c=c7_line<L,DY,DX,0>(p);
    ap_int<14> l=ap_int<14>(c7_line<L,DY,DX,DIST>(p))-c;
    ap_int<14> r=ap_int<14>(c7_line<L,DY,DX,-DIST>(p))-c;
    small=l<r?l:r;
    imbalance=l<r?ap_uint<13>(r-l):ap_uint<13>(l-r);
    ap_uint<8> a=c7_at<-DIST*DX,DIST*DY>(p),b=c7_at<DIST*DX,-DIST*DY>(p);
    central=ap_int<10>(a<b?a:b)-ap_int<10>(c7_at<0,0>(p));
}

template<int L,int DIST,typename T>
static void c7_bilateral(hls::Window<17,17,T>& p,ap_int<10> f[36],int index) {
#pragma HLS INLINE
    ap_int<14> small[4]; ap_uint<13> imbalance[4]; ap_int<10> central[4];
#pragma HLS ARRAY_PARTITION variable=small complete
#pragma HLS ARRAY_PARTITION variable=imbalance complete
#pragma HLS ARRAY_PARTITION variable=central complete
    c7_pair<L,0,1,DIST>(p,small[0],imbalance[0],central[0]);
    c7_pair<L,1,0,DIST>(p,small[1],imbalance[1],central[1]);
    c7_pair<L,1,1,DIST>(p,small[2],imbalance[2],central[2]);
    c7_pair<L,1,-1,DIST>(p,small[3],imbalance[3],central[3]);
    ap_int<14> best=small[0]; ap_uint<13> chosen=imbalance[0]; ap_int<10> center=central[0];
    for(int i=1;i<4;++i) {
#pragma HLS UNROLL
        if(small[i]>best) {best=small[i];chosen=imbalance[i];center=central[i];}
    }
    f[index]=c7_round<L>(best); f[index+1]=(chosen+L/2)/L; f[index+2]=center;
}

template<int L,typename T>
static void c7_lines(hls::Window<17,17,T>& p,ap_uint<8> m7,ap_uint<8> m15,ap_int<10> f[36],int index) {
#pragma HLS INLINE
    ap_uint<8> means[4];
#pragma HLS ARRAY_PARTITION variable=means complete
    means[0]=(c7_line<L,0,1,0>(p)+L/2)/L; means[1]=(c7_line<L,1,0,0>(p)+L/2)/L;
    means[2]=(c7_line<L,1,1,0>(p)+L/2)/L; means[3]=(c7_line<L,1,-1,0>(p)+L/2)/L;
    ap_uint<8> low=means[0],high=means[0];
    for(int i=1;i<4;++i) {
#pragma HLS UNROLL
        if(means[i]<low) low=means[i]; if(means[i]>high) high=means[i];
    }
    f[index]=ap_int<10>(m7)-ap_int<10>(low); f[index+1]=ap_int<10>(m15)-ap_int<10>(low);
    f[index+2]=ap_int<10>(high)-ap_int<10>(low); f[index+3]=ap_int<10>(low)-ap_int<10>(c7_at<0,0>(p));
}

template<typename T>
static void c7_features(hls::Window<17,17,T>& p,ap_int<10> f[36]) {
#pragma HLS INLINE
    ap_uint<8> g=c7_at<0,0>(p),m3=c7_mean<3>(p),m7=c7_mean<7>(p);
    ap_uint<16> sum15;ap_uint<8> low,high;
    C7Reduce<15,0,225>::run(p,sum15,low,high);
    ap_uint<8> m15=(sum15+112)/225;
    f[0]=g; f[1]=ap_int<10>(m3)-ap_int<10>(g); f[2]=ap_int<10>(m7)-ap_int<10>(g); f[3]=ap_int<10>(m15)-ap_int<10>(g);
    f[4]=ap_int<10>(high)-ap_int<10>(g); f[5]=ap_int<10>(g)-ap_int<10>(low);
    c7_lines<5>(p,m7,m15,f,6); c7_bilateral<5,1>(p,f,10); c7_bilateral<5,2>(p,f,13); c7_bilateral<5,4>(p,f,16);
    c7_lines<9>(p,m7,m15,f,19); c7_bilateral<9,1>(p,f,23); c7_bilateral<9,2>(p,f,26); c7_bilateral<9,4>(p,f,29);
    c7_lines<15>(p,m7,m15,f,32);
}

class C7Kernel {
public:
    template<typename S,typename D,typename K,int H,int W>
    void apply(hls::Window<H,W,K>& coefficients,hls::Window<H,W,S>& p,D& dst) {
#pragma HLS INLINE
        ap_int<10> f[36];
#pragma HLS ARRAY_PARTITION variable=f complete
        c7_features(p,f);
        ap_uint<16> result=c7_forest(f);
        result[8]=ap_uint<16>(p.val[8][8])[8];
        dst=result;
    }
};

#ifndef __SYNTHESIS__
void c7_test_features(const unsigned char* green,int side,int y,int x,int* features) {
    hls::Window<17,17,unsigned short> p;
    for(int i=0;i<17;++i) for(int j=0;j<17;++j) {
        int yy=y+8-i,xx=x+8-j;
        yy=yy<0?0:yy>=side?side-1:yy;xx=xx<0?0:xx>=side?side-1:xx;
        p.val[i][j]=green[yy*side+xx];
    }
    ap_int<10> values[36];c7_features(p,values);
    for(int i=0;i<36;++i) features[i]=values[i];
}
#endif

static void c7_filter(C7Plane& input,C7Plane& output) {
#pragma HLS INLINE off
    hls::Window<17,17,ap_uint<1> > kernel;
    for(int y=0;y<17;++y) for(int x=0;x<17;++x) {
#pragma HLS UNROLL
        kernel.val[y][x]=0;
    }
    hls::filter_opr<C7Kernel,hls::BORDER_REPLICATE>::filter(input,output,kernel,hls::Point_<int>(8,8),input.rows,input.cols);
}

static void c7_fork(hls::stream<ap_uint<32> >& source,hls::stream<ap_uint<32> >& base,C7Plane& raw,int count) {
    for(int i=0;i<count;++i) {
#pragma HLS PIPELINE II=1
        ap_uint<32> word=source.read(); base.write(word);
        ap_uint<16> value=word.range(15,8);value[8]=word[24];
        hls::Scalar<1,unsigned short> p;p.val[0]=value;raw.write(p);
    }
}

static void c7_join(hls::stream<ap_uint<32> >& base,C7Plane& score,hls::stream<ap_uint<32> >& output,int count,ap_uint<32> control) {
    for(int i=0;i<count;++i) {
#pragma HLS PIPELINE II=1
        ap_uint<32> word=base.read(); ap_uint<16> s=score.read().val[0];
        if(control[5]&&(control.range(1,0)==3)) {
            word.range(23,16)=(s[8]&&(s.range(7,0)>=control.range(15,8)))?255:0;
            word.range(31,24)=s.range(7,0);
        }
        output.write(word);
    }
}

void retina_detector_hls(hls::stream<ap_uint<32> >& source,hls::stream<ap_uint<32> >& result,ap_uint<32> control) {
#pragma HLS INTERFACE axis port=source
#pragma HLS INTERFACE axis port=result
#pragma HLS INTERFACE ap_none port=control
#pragma HLS INTERFACE ap_ctrl_hs port=return
#pragma HLS DATAFLOW
    int side=control[2]?256:512,count=side*side;
    hls::stream<ap_uint<32> > base_source,base_result;
    C7Plane raw(side,side),score(side,side);
#pragma HLS STREAM variable=base_source depth=32
#pragma HLS STREAM variable=base_result depth=32
#pragma HLS STREAM variable=raw.data_stream depth=32
#pragma HLS STREAM variable=score.data_stream depth=32768
#pragma HLS RESOURCE variable=score.data_stream core=FIFO_BRAM
    c7_fork(source,base_source,raw,count);
    retina_detector_c5(base_source,base_result,control);
    c7_filter(raw,score);
    c7_join(base_result,score,result,count,control);
}
