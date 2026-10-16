#include "retina_quality_hls.hpp"
#include <cstdio>
#include <vector>

static unsigned int random_state=0x154271b1;
static unsigned int next_random() {
    random_state^=random_state<<13; random_state^=random_state>>17; random_state^=random_state<<5;
    return random_state;
}
static int clamp(int value,int side) { return value<0?0:(value>=side?side-1:value); }
static int run_case(int side,int mode,int pattern,int algorithm=0,int threshold=28) {
    const int count=side*side;
    std::vector<unsigned int> words(count);
    std::vector<int> enhanced(count),background(count),response(count),initial(count),dilated(count),closed(count);
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
            case 7:g=(x*13+y*7+9)%80;break;
            case 8:case 9:case 12:g=(x%31<5||y%43<3)?12:190;break;
            case 10:g=(x==side/2&&y==side/2)?168:192;break;
            default:g=(y>=side/2-1&&y<=side/2+1&&x>32&&x<side-32&&x!=side/2)?120:192;break;
        }
        int fov=(x+y)&1;
        if(pattern==8)fov=0;
        else if(pattern==9)fov=(x<side/2&&y>=side/4&&y<3*side/4);
        else if(pattern>=10)fov=1;
        words[i]=(unsigned(fov)<<24)|(((i*7)&255)<<16)|(g<<8)|((i*13)&255);
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
    for(int i=0;i<count;++i) {
        int y=i/side,x=i%side,sum=0;
        for(int dy=-7;dy<=7;++dy) for(int dx=-7;dx<=7;++dx)
            sum+=enhanced[clamp(y+dy,side)*side+clamp(x+dx,side)];
        background[i]=(sum+112)/225;
        int value=4*(background[i]-enhanced[i]);
        response[i]=value<0?0:(value>255?255:value);
        if(algorithm) {
            const int dirs[4][2]={{0,1},{1,0},{1,1},{1,-1}};
            bool supported=false;
            for(int dir=0;dir<4;++dir)for(int d=1;d<=5;++d) {
                int c=0,l=0,r=0;
                const int dy=dirs[dir][0],dx=dirs[dir][1];
                for(int t=-4;t<=4;++t) {
                    c+=enhanced[clamp(y+t*dy,side)*side+clamp(x+t*dx,side)];
                    l+=enhanced[clamp(y+t*dy-d*dx,side)*side+clamp(x+t*dx+d*dy,side)];
                    r+=enhanced[clamp(y+t*dy+d*dx,side)*side+clamp(x+t*dx-d*dy,side)];
                }
                supported|=(l-c>=9&&r-c>=9);
            }
            if(!supported)response[i]=response[i]>28?response[i]-28:0;
        }
        initial[i]=(response[i]>=threshold)&&((words[i]>>24)!=0);
    }
    const int dy[5]={-1,0,0,0,1},dx[5]={0,-1,0,1,0};
    for(int i=0;i<count;++i) {
        int y=i/side,x=i%side,value=0;
        for(int k=0;k<5;++k) {
            int yy=y+dy[k],xx=x+dx[k];
            if(yy>=0&&yy<side&&xx>=0&&xx<side)value|=initial[yy*side+xx];
        }
        dilated[i]=value;
    }
    for(int i=0;i<count;++i) {
        int y=i/side,x=i%side,value=1;
        for(int k=0;k<5;++k) {
            int yy=y+dy[k],xx=x+dx[k];
            value&=(yy>=0&&yy<side&&xx>=0&&xx<side)?dilated[yy*side+xx]:0;
        }
        closed[i]=value;
    }
    retina_quality_hls(input,output,(side==256?4:0)|mode|(algorithm?8:0)|(threshold<<8));
    for(int i=0;i<count;++i) {
        int y=i/side,x=i%side,neighbours=0;
        for(int dy=-1;dy<=1;++dy) for(int dx=-1;dx<=1;++dx)
            neighbours+=closed[clamp(y+dy,side)*side+clamp(x+dx,side)];
        int mask=mode==1?initial[i]:(mode==2?closed[i]:(closed[i]&&neighbours>=2&&((words[i]>>24)!=0)));
        unsigned int expected=mode==0?words[i]:((words[i]>>8)&255)|(unsigned(enhanced[i])<<8)|
                              (unsigned(mask?255:0)<<16)|(unsigned(response[i])<<24);
        if(output.empty()) { std::printf("ERROR: missing output index=%d\n",i);return 1; }
        unsigned int actual=output.read();
        if(actual!=expected) {
            std::printf("ERROR: side=%d mode=%d pattern=%d y=%d x=%d actual=%08x expected=%08x bg_sum=%d\n",
                        side,mode,pattern,y,x,actual,expected,background[i]);return 1;
        }
    }
    if(!input.empty()||!output.empty()) { std::printf("ERROR: extra words\n");return 1; }
    std::printf("Q2_QUALITY_PIPELINE_CASE_PASS: %d stage %d pattern %d algorithm %d threshold %d words %d\n",side,mode,pattern,algorithm,threshold,count);
    return 0;
}
static int primitive_probe() {
    typedef hls::Mat<512,512,HLS_8UC1> Image;
    hls::Scalar<1,unsigned char> pixel;
    Image a(4,4),b(4,4),c(4,4),d(4,4);
    const unsigned char levels[4]={0,27,28,255};
    for(int y=0;y<4;++y)for(int x=0;x<4;++x) {pixel.val[0]=levels[x];a.write(pixel);}
    hls::Threshold(a,b,(unsigned char)27,(unsigned char)1,HLS_THRESH_BINARY);
    for(int y=0;y<4;++y)for(int x=0;x<4;++x)
        if(b.read().val[0]!=(levels[x]>=28)) {std::printf("ERROR: threshold >=28 boundary\n");return 1;}
    hls::Window<3,3,unsigned char> cross;
    const unsigned char values[3][3]={{0,1,0},{1,1,1},{0,1,0}};
    for(int y=0;y<3;++y)for(int x=0;x<3;++x)cross.val[y][x]=values[y][x];
    for(int y=0;y<4;++y)for(int x=0;x<4;++x) {pixel.val[0]=1;c.write(pixel);}
    hls::morp_opr<hls::erode_kernel,hls::BORDER_CONSTANT,hls::MORPH_CROSS,1>(c,d,cross,hls::Point_<int>(1,1));
    for(int y=0;y<4;++y)for(int x=0;x<4;++x)
        if(d.read().val[0]!=(y>0&&y<3&&x>0&&x<3)) {std::printf("ERROR: erode constant-zero edge\n");return 1;}
    std::printf("VENDOR_SEGMENTATION_PRIMITIVES_PASS: response 0/27/28/255; zero-border erosion\n");
    return 0;
}
int main() {
    if(primitive_probe()||run_case(256,0,0)||run_case(256,1,1)||run_case(256,2,0)||run_case(512,3,1)||
       run_case(256,1,2)||run_case(256,2,3)||run_case(256,3,4)||run_case(256,3,5)||
       run_case(512,3,6)||run_case(256,3,7)||run_case(512,3,8)||run_case(256,3,9)||
       run_case(256,3,10)||run_case(512,3,11)||run_case(256,2,12)||run_case(512,3,12))return 1;
    if(run_case(256,1,1,1,28)||run_case(512,3,11,1,28)||run_case(256,0,2,1,1)||
       run_case(256,2,9,1,255)||run_case(256,3,10,1,27)||run_case(256,3,12,1,28)||
       run_case(256,3,12,1,29)||run_case(512,1,6,1,1))return 1;
    std::printf("Q2_QUALITY_PIPELINE_CSIM_PASS: 24 full frames, 2949120 exact words; 16 A/T28 compatibility, 8 C2 and dynamic threshold cases; CPU Csim only\n");
    return 0;
}
