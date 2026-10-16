// Experimental fixed C5_l5_9_r8_m1_a4_g3, selected under the user's
// documented visual/overall-quality tradeoff. Old strict-gate failures remain.
// All medical filtering and finite gap decisions below execute in PL.
#include "retina_detector_hls.hpp"

typedef hls::Mat<512,512,HLS_8UC1> RefImage;
typedef hls::Mat<512,512,HLS_16UC1> RefSum;

static void fork_input(hls::stream<ap_uint<32> >& source,
                       hls::stream<ap_uint<32> >& base, RefImage& green,
                       hls::stream<ap_uint<1> >& fov, int count) {
    for(int i=0;i<count;++i) {
#pragma HLS PIPELINE II=1
        ap_uint<32> word=source.read();
        hls::Scalar<1,unsigned char> p; p.val[0]=word.range(15,8);
        base.write(word); green.write(p); fov.write(word[24]);
    }
}

static void gaussian_sum(RefImage& green, RefSum& sums) {
    hls::Window<3,3,ap_uint<4> > kernel;
    const unsigned char weights[3][3]={{1,2,1},{2,4,2},{1,2,1}};
    for(int y=0;y<3;++y) for(int x=0;x<3;++x) {
#pragma HLS UNROLL
        kernel.val[y][x]=weights[y][x];
    }
    hls::Filter2D<hls::BORDER_REPLICATE>(green,sums,kernel,hls::Point_<int>(1,1));
}

static void gaussian_round(RefSum& sums, RefImage& filtered, int count) {
    for(int i=0;i<count;++i) {
#pragma HLS PIPELINE II=1
        hls::Scalar<1,unsigned short> s=sums.read();
        hls::Scalar<1,unsigned char> p; p.val[0]=(ap_uint<12>(s.val[0])+ap_uint<12>(8))>>4;
        filtered.write(p);
    }
}

template<int DY,int DX,int DIST,int LEN,typename T>
static ap_uint<2> profile_pair(hls::Window<19,19,T>& pixels) {
#pragma HLS INLINE
    ap_int<13> l=0,r=0;
    ap_uint<4> positive=0;
    ap_uint<1> central=0;
    for(int i=0;i<LEN;++i) {
#pragma HLS UNROLL
        const int t=i-LEN/2;
        ap_int<10> c=ap_uint<8>(pixels.val[9-t*DY][9-t*DX]);
        ap_int<10> dl=ap_int<10>(ap_uint<8>(pixels.val[9-(t*DY-DIST*DX)][9-(t*DX+DIST*DY)]))-c;
        ap_int<10> dr=ap_int<10>(ap_uint<8>(pixels.val[9-(t*DY+DIST*DX)][9-(t*DX-DIST*DY)]))-c;
        l+=dl; r+=dr;
        ap_uint<1> yes=(dl>0)&&(dr>0);
        positive+=yes;
        if(i==LEN/2) central=yes;
    }
    ap_int<13> small=l<r?l:r,large=l<r?r:l;
    ap_uint<1> balanced=ap_int<17>(large)<=(ap_int<17>(small)<<3);
    ap_uint<2> out=0;
    out[0]=(small>=LEN)&&balanced;
    out[1]=(small>=4*LEN)&&balanced&&central&&(ap_uint<7>(positive)*3>=2*LEN);
    return out;
}

template<int DY,int DX,int LEN,typename T>
static ap_uint<2> profile_scale(hls::Window<19,19,T>& p) {
#pragma HLS INLINE
    return profile_pair<DY,DX,1,LEN>(p)|profile_pair<DY,DX,2,LEN>(p)|
           profile_pair<DY,DX,3,LEN>(p)|profile_pair<DY,DX,4,LEN>(p)|profile_pair<DY,DX,5,LEN>(p);
}

template<int DY,int DX,typename T>
static ap_uint<2> profile_direction(hls::Window<19,19,T>& p) {
#pragma HLS INLINE
    ap_uint<2> a=profile_scale<DY,DX,5>(p),b=profile_scale<DY,DX,9>(p),out=0;
    out[0]=a[0]|b[0]; out[1]=a[1]&b[1]; return out;
}

class RefEvidenceKernel {
public:
    template<typename S,typename D,typename K,int H,int W>
    void apply(hls::Window<H,W,K>& coefficients,hls::Window<H,W,S>& p,D& dst) {
#pragma HLS INLINE
        ap_uint<2> a=profile_direction<0,1>(p),b=profile_direction<1,0>(p),
                   c=profile_direction<1,1>(p),d=profile_direction<1,-1>(p);
        ap_uint<8> bits=0;
        bits[0]=a[0]|b[0]|c[0]|d[0];
        bits[1]=a[1]; bits[2]=b[1]; bits[3]=c[1]; bits[4]=d[1];
        dst=bits;
    }
};

static void profile_evidence(RefImage& filtered,RefImage& output) {
#pragma HLS INLINE off
    hls::Window<19,19,ap_uint<1> > kernel;
    for(int y=0;y<19;++y) for(int x=0;x<19;++x) {
#pragma HLS UNROLL
        kernel.val[y][x]=0;
    }
    hls::filter_opr<RefEvidenceKernel,hls::BORDER_REPLICATE>::filter(
        filtered,output,kernel,hls::Point_<int>(9,9),filtered.rows,filtered.cols);
}

static void seed_flags(hls::stream<ap_uint<32> >& base,RefImage& evidence,
                       hls::stream<ap_uint<1> >& fov, RefImage& flags,
                       hls::stream<ap_uint<32> >& aligned,int count) {
    for(int i=0;i<count;++i) {
#pragma HLS PIPELINE II=1
        ap_uint<32> word=base.read();
        ap_uint<8> bits=evidence.read().val[0]; ap_uint<1> valid=fov.read();
        bits[0]=bits[0]&&(word.range(23,16)!=0)&&valid;
        bits[5]=valid;
        hls::Scalar<1,unsigned char> p; p.val[0]=bits;
        flags.write(p); aligned.write(word);
    }
}

template<int DY,int DX,int DIR,typename T>
static ap_uint<1> supported_gap(hls::Window<7,7,T>& p) {
#pragma HLS INLINE
    ap_uint<1> accepted=0;
    for(int gap=1;gap<=3;++gap) {
#pragma HLS UNROLL
        for(int position=1;position<=3;++position) {
#pragma HLS UNROLL
            if(position<=gap) {
                ap_uint<1> valid=1;
                for(int step=0;step<=4;++step) {
#pragma HLS UNROLL
                    if(step<=gap+1) {
                        int delta=step-position;
                        ap_uint<8> item=p.val[3-delta*DY][3-delta*DX];
                        ap_uint<1> endpoint=(step==0)||(step==gap+1);
                        valid=valid&&item[5]&&item[1+DIR]&&(endpoint?item[0]:ap_uint<1>(!item[0]));
                    }
                }
                accepted|=valid;
            }
        }
    }
    return accepted;
}

class RefGapKernel {
public:
    template<typename S,typename D,typename K,int H,int W>
    void apply(hls::Window<H,W,K>& coefficients,hls::Window<H,W,S>& p,D& dst) {
#pragma HLS INLINE
        ap_uint<8> center=p.val[3][3];
        dst=center[5]&&(center[0]||supported_gap<0,1,0>(p)||supported_gap<1,0,1>(p)||
                                    supported_gap<1,1,2>(p)||supported_gap<1,-1,3>(p));
    }
};

static void finite_gap_filter(RefImage& flags,RefImage& output) {
#pragma HLS INLINE off
    hls::Window<7,7,ap_uint<1> > kernel;
    for(int y=0;y<7;++y) for(int x=0;x<7;++x) {
#pragma HLS UNROLL
        kernel.val[y][x]=0;
    }
    hls::filter_opr<RefGapKernel,hls::BORDER_CONSTANT>::filter(
        flags,output,kernel,hls::Point_<int>(3,3),flags.rows,flags.cols);
}

static void refined_join(RefImage& mask,hls::stream<ap_uint<32> >& aligned,
                         hls::stream<ap_uint<32> >& result,int count,ap_uint<1> active) {
    for(int i=0;i<count;++i) {
#pragma HLS PIPELINE II=1
        ap_uint<1> value=mask.read().val[0]!=0;
        ap_uint<32> word=aligned.read();
        if(active) word.range(23,16)=value?255:0;
        result.write(word);
    }
}

void retina_detector_c5(hls::stream<ap_uint<32> >& source,
                        hls::stream<ap_uint<32> >& result,ap_uint<32> control) {
#pragma HLS DATAFLOW
    int side=control[2]?256:512,count=side*side;
    hls::stream<ap_uint<32> > base_source,base_result,aligned;
    hls::stream<ap_uint<1> > fov;
    RefImage green(side,side),filtered(side,side),evidence(side,side),flags(side,side),mask(side,side);
    RefSum sums(side,side);
#pragma HLS STREAM variable=base_source depth=32
#pragma HLS STREAM variable=base_result depth=32
#pragma HLS STREAM variable=green.data_stream depth=32
#pragma HLS STREAM variable=sums.data_stream depth=32
#pragma HLS STREAM variable=filtered.data_stream depth=32
#pragma HLS STREAM variable=evidence.data_stream depth=16384
#pragma HLS RESOURCE variable=evidence.data_stream core=FIFO_BRAM
#pragma HLS STREAM variable=fov depth=16384
#pragma HLS RESOURCE variable=fov core=FIFO_BRAM
#pragma HLS STREAM variable=flags.data_stream depth=32
#pragma HLS STREAM variable=mask.data_stream depth=32
#pragma HLS STREAM variable=aligned depth=4096
#pragma HLS RESOURCE variable=aligned core=FIFO_BRAM
    fork_input(source,base_source,green,fov,count);
    retina_refined_base(base_source,base_result,control);
    gaussian_sum(green,sums);
    gaussian_round(sums,filtered,count);
    profile_evidence(filtered,evidence);
    seed_flags(base_result,evidence,fov,flags,aligned,count);
    finite_gap_filter(flags,mask);
    refined_join(mask,aligned,result,count,control[4]&&(control.range(1,0)==3));
}
