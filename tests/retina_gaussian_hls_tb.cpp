#include "retina_gaussian_hls.hpp"
#include <cstdio>
#include <vector>
#include <cstdlib>

static unsigned int random_state=0x154271b1;
static unsigned int next_random() {
    random_state^=random_state<<13; random_state^=random_state>>17; random_state^=random_state<<5;
    return random_state;
}

static int run_case(int side,int mode,int pattern) {
    int count=side*side;
    std::vector<unsigned int> words(count);
    hls::stream<ap_uint<32> > input,output;
    for(int i=0;i<count;++i) {
        int y=i/side,x=i%side,g=0;
        switch(pattern) {
            case 0: g=(x*11+y*17)&255; break;
            case 1: g=next_random()&255; break;
            case 2: g=255; break;
            case 3: g=((x&1)^(y&1))?255:0; break;
            default: g=((x==0||x==side-1||x==side/2)&&(y==0||y==side-1||y==side/2))?255:0; break;
        }
        words[i]=(((x+y)&1)<<24)|(((i*7)&255)<<16)|(g<<8)|((i*13)&255);
        input.write(words[i]);
    }
    retina_gaussian_hls(input,output,(side==256?4:0)|mode);
    for(int i=0;i<count;++i) {
        int y=i/side,x=i%side,sum=0;
        for(int dy=-1;dy<=1;++dy) for(int dx=-1;dx<=1;++dx) {
            int sy=y+dy,sx=x+dx;
            if(sy<0)sy=0; if(sy>=side)sy=side-1;
            if(sx<0)sx=0; if(sx>=side)sx=side-1;
            sum+=((words[sy*side+sx]>>8)&255)*(dy==0?2:1)*(dx==0?2:1);
        }
        unsigned int gaussian=(sum+8)/16,value=gaussian;
        if(mode==1)value=(words[i]>>8)&255;
        if(mode==3) { value=(gaussian*255+96)/192; if(value>255)value=255; }
        unsigned int expected=mode==0?words[i]:((words[i]&0xff000000)|(((words[i]>>8)&255))|(value<<8));
        if(output.empty()) { std::printf("ERROR: missing output at %d\n",i); return 1; }
        unsigned int actual=output.read();
        if(actual!=expected) {
            std::printf("ERROR: side=%d mode=%d pattern=%d y=%d x=%d actual=%08x expected=%08x sum=%d\n",side,mode,pattern,y,x,actual,expected,sum);
            return 1;
        }
    }
    if(!input.empty()||!output.empty()) { std::printf("ERROR: extra words\n"); return 1; }
    std::printf("VENDOR_FILTER_CASE_PASS: %d mode %d pattern %d pixels %d\n",side,mode,pattern,count);
    return 0;
}
int main() {
    if(run_case(256,2,0)||run_case(512,3,1)||run_case(256,3,4)||run_case(256,2,2)||
       run_case(256,3,3)||run_case(512,2,4)||run_case(256,0,1)||run_case(256,1,0)) return 1;
    std::printf("VENDOR_GAUSSIAN_CSIM_PASS: 8 full frames, 917504 exact words; replicate borders, rounding, center FOV/G, modes\n");
    return 0;
}
