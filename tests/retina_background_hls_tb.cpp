#include "retina_background_hls.hpp"
#include <cstdio>
#include <vector>

static unsigned int random_state=0x154271b1;
static unsigned int next_random() {
    random_state^=random_state<<13; random_state^=random_state>>17; random_state^=random_state<<5;
    return random_state;
}
static int clamp(int value,int side) { return value<0?0:(value>=side?side-1:value); }
static int run_case(int side,int mode,int pattern) {
    const int count=side*side;
    std::vector<unsigned int> words(count);
    std::vector<int> enhanced(count);
    hls::stream<ap_uint<32> > input,output;
    for(int i=0;i<count;++i) {
        int y=i/side,x=i%side,g=0;
        switch(pattern) {
            case 0:g=(x*11+y*17)&255;break;
            case 1:g=next_random()&255;break;
            case 2:g=((x==0||x==side-1||x==side/2)&&(y==0||y==side-1||y==side/2))?255:0;break;
            case 3:g=((x&1)^(y&1))?255:0;break;
            case 4:g=255;break;
            case 5:g=0;break;
            case 6:g=(x%31<5||y%43<3)?12:190;break;
            default:g=(x*13+y*7+9)%80;break;
        }
        words[i]=(((x+y)&1)<<24)|(((i*7)&255)<<16)|(g<<8)|((i*13)&255);
        input.write(words[i]);
    }
    // Independent nine-point reference, followed by all 225 integer samples.
    for(int i=0;i<count;++i) {
        int y=i/side,x=i%side,sum=0;
        for(int dy=-1;dy<=1;++dy) for(int dx=-1;dx<=1;++dx)
            sum+=((words[clamp(y+dy,side)*side+clamp(x+dx,side)]>>8)&255)*(dy==0?2:1)*(dx==0?2:1);
        int gaussian=(sum+8)/16;
        int value=(gaussian*255+96)/192;
        enhanced[i]=value>255?255:value;
    }
    retina_background_hls(input,output,(side==256?4:0)|mode);
    for(int i=0;i<count;++i) {
        int y=i/side,x=i%side,sum=0;
        for(int dy=-7;dy<=7;++dy) for(int dx=-7;dx<=7;++dx)
            sum+=enhanced[clamp(y+dy,side)*side+clamp(x+dx,side)];
        unsigned int background=(sum+112)/225;
        int response=4*(int(background)-enhanced[i]);
        if(response<0)response=0;if(response>255)response=255;
        unsigned int expected=words[i];
        if(mode!=0) expected=((words[i]>>8)&255)|(enhanced[i]<<8)|((mode==1?0:background)<<16)|
                             (mode==3?(unsigned(response)<<24):(words[i]&0xff000000));
        if(output.empty()) { std::printf("ERROR: missing output index=%d\n",i);return 1; }
        unsigned int actual=output.read();
        if(actual!=expected) {
            std::printf("ERROR: side=%d mode=%d pattern=%d y=%d x=%d actual=%08x expected=%08x bg_sum=%d\n",
                        side,mode,pattern,y,x,actual,expected,sum);return 1;
        }
    }
    if(!input.empty()||!output.empty()) { std::printf("ERROR: extra words\n");return 1; }
    std::printf("VENDOR_BACKGROUND_CASE_PASS: %d mode %d pattern %d words %d\n",side,mode,pattern,count);
    return 0;
}
int main() {
    if(run_case(256,0,0)||run_case(256,1,1)||run_case(256,2,0)||run_case(512,3,1)||
       run_case(256,2,2)||run_case(256,3,3)||run_case(256,2,4)||run_case(256,3,5)||
       run_case(512,2,2)||run_case(256,3,6)||run_case(256,2,7)||run_case(512,3,7)) return 1;
    std::printf("VENDOR_BACKGROUND_CSIM_PASS: 12 full frames, 1376256 exact words; Gaussian, LUT, 15x15 replicated background, signed saturated response\n");
    return 0;
}
