#include "retina_c2_support_hls.hpp"
#include <cstdio>
#include <vector>

static unsigned int rng=0x2c241014;
static unsigned int next_random() {
    rng^=rng<<13; rng^=rng>>17; rng^=rng<<5;
    return rng;
}
static int clamp(int n,int side) {return n<0?0:n>=side?side-1:n;}
static int pixel(int side,int pattern,int y,int x) {
    const int cy=side/2,cx=side/2;
    if(pattern==0)return 0;
    if(pattern==1)return 255;
    if(pattern==2)return x<cx?0:255;
    if(pattern==3)return y<cy?255:0;
    if(pattern==4)return x+y<side?0:255;
    if(pattern==5)return x-y<0?255:0;
    if(pattern==6)return y==cy?80:180;
    if(pattern==7)return x==cx?80:180;
    if(pattern==8)return x==y?80:180;
    if(pattern==9)return x+y==side-1?80:180;
    if(pattern==10)return (x-cx>=-3&&x-cx<=3)?80:180;
    if(pattern==11)return (y-cy>=-4&&y-cy<=4)?80:180;
    if(pattern==12)return (x==cx||y==cy||x==y)?80:180;
    if(pattern==13)return ((x+y)&1)?255:0;
    if(pattern==14)return (x==0||y==0||x==side-1||y==side-1)?0:255;
    if(pattern==15)return (x==0&&y==0)||(x==side-1&&y==side-1)?0:255;
    if(pattern==16)return (x>=cx-4&&x<=cx+4&&y>=cy-8&&y<=cy+8)?245:100;
    if(pattern==17)return y==cy?30:(x>=cx-6&&x<=cx+6?245:130);
    if(pattern==18)return y==cy?179:180; // exact nine-sample margin
    if(pattern==19)return (y==cy&&x!=cx)?179:180; // eight is below margin
    if(pattern==20)return ((x*11+y*17)&255);
    return next_random()&255;
}
static bool reference_support(const std::vector<int>& image,int side,int y,int x) {
    const int directions[4][2]={{0,1},{1,0},{1,1},{1,-1}};
    for(int direction=0;direction<4;++direction) {
        const int dy=directions[direction][0],dx=directions[direction][1];
        for(int distance=1;distance<=5;++distance) {
            // Independent scalar image coordinates and int sums.
            int c=0,l=0,r=0;
            for(int t=-4;t<=4;++t) {
                c+=image[clamp(y+t*dy,side)*side+clamp(x+t*dx,side)];
                l+=image[clamp(y+t*dy-distance*dx,side)*side+clamp(x+t*dx+distance*dy,side)];
                r+=image[clamp(y+t*dy+distance*dx,side)*side+clamp(x+t*dx-distance*dy,side)];
            }
            if(l-c>=9&&r-c>=9)return true;
        }
    }
    return false;
}
static int run_case(int side,int pattern) {
    const int count=side*side;
    std::vector<int> enhanced(count),responses(count),tags(count);
    hls::stream<ap_uint<32> > source,result;
    const int response_levels[8]={0,1,27,28,29,55,56,255};
    for(int i=0;i<count;++i) {
        enhanced[i]=pixel(side,pattern,i/side,i%side);
        responses[i]=response_levels[i%8];
        tags[i]=(i*137+pattern*31)&65535;
        source.write((unsigned(tags[i])<<16)|(unsigned(responses[i])<<8)|unsigned(enhanced[i]));
    }
    retina_c2_support_hls(source,result,side);
    int accepted=0;
    for(int i=0;i<count;++i) {
        bool support=reference_support(enhanced,side,i/side,i%side);
        int response=support?responses[i]:(responses[i]>28?responses[i]-28:0);
        unsigned int expected=(unsigned(tags[i])<<16)|(unsigned(support)<<8)|unsigned(response);
        if(result.empty()) {std::printf("ERROR: missing pixel %d\n",i);return 1;}
        unsigned int actual=result.read();
        if(actual!=expected) {
            std::printf("ERROR: side=%d pattern=%d y=%d x=%d actual=%08x expected=%08x\n",
                        side,pattern,i/side,i%side,actual,expected);
            return 1;
        }
        accepted+=support;
    }
    if(!source.empty()||!result.empty()) {std::printf("ERROR: extra pixels\n");return 1;}
    std::printf("C2_SUPPORT_CASE_PASS: side=%d pattern=%d words=%d accepted=%d\n",side,pattern,count,accepted);
    return 0;
}
int main() {
    for(int pattern=0;pattern<22;++pattern)if(run_case(32,pattern))return 1;
    if(run_case(256,21)||run_case(512,17)||run_case(256,20)||run_case(512,21)||run_case(32,18))return 1;
    std::printf("C2_SUPPORT_CSIM_PASS: 27 frames; 678912 exact words; scalar borders/support/penalty/tags; CPU C simulation only\n");
    return 0;
}
