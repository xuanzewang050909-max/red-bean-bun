#include <stdint.h>
#include "geometry.hpp"
// 6 planes of uint32: input, smooth/FOV, response, active0, active1, final.
// Input RGB low24, FOV bit24, old mask bit25. No label/coordinate/answer ROM.
static uint32_t cache[32][512];
static int phase=0, grows=0;
static int clamp(int x,int n){return x<0?0:(x>=n?n-1:x);}
static uint32_t get(int y,int x,int h,int w){return cache[clamp(y,h)&31][clamp(x,w)];}
static void loadrow(volatile uint32_t *mem,int base,int y,int h,int w){
    if(y>=0 && y<h){
        for(int x=0;x<w;++x){
#pragma HLS PIPELINE II=1
            cache[y&31][x]=mem[base+y*w+x];
        }
    }
}
extern "C" int valley_repair(volatile uint32_t *mem, int op, int height,int width,int capacity){
#pragma HLS INTERFACE m_axi port=mem offset=slave bundle=ram depth=1572864 max_read_burst_length=16 max_write_burst_length=16 num_read_outstanding=1 num_write_outstanding=1
#pragma HLS INTERFACE s_axilite port=mem bundle=control
#pragma HLS INTERFACE s_axilite port=op bundle=control
#pragma HLS INTERFACE s_axilite port=height bundle=control
#pragma HLS INTERFACE s_axilite port=width bundle=control
#pragma HLS INTERFACE s_axilite port=capacity bundle=control
#pragma HLS INTERFACE s_axilite port=return bundle=control
#pragma HLS RESOURCE variable=cache core=RAM_T2P_BRAM
    if(height<1 || width<1 || height>512 || width>512)return 1;
    const int n=height*width;
    if(capacity<6*n || op<0 || op>4)return 2;
    if(op!=0 && ((op==1 && phase!=1)||(op==2 && phase!=2)||(op==3 && (phase!=3 || grows>=16))||(op==4 && (phase!=3 || grows!=16))))return 3;
    int base=op==0?0:op==1?n:op==2?2*n:((op==3?(grows&1):(grows&1))?4*n:3*n);
    int dest=op==0?n:op==1?2*n:op==2?3*n:op==3?((grows&1)?3*n:4*n):5*n;
    for(int y=0;y<16 && y<height;++y)loadrow(mem,base,y,height,width);
    for(int y=0;y<height;++y){
        loadrow(mem,base,y+16,height,width);
        for(int x=0;x<width;++x){
            uint32_t value=0;
            if(op==0){
                int sum=0;
                for(int dy=-1;dy<=1;++dy)for(int dx=-1;dx<=1;++dx){
                    sum+=int((get(y+dy,x+dx,height,width)>>8)&255)*(dy==0?2:1)*(dx==0?2:1);
                }
                bool f=true;
                for(int dx=-12;dx<=12;++dx)f=f && x+dx>=0 && x+dx<width && ((get(y,x+dx,height,width)>>24)&1);
                value=uint32_t(sum)|(uint32_t(f)<<12)|((get(y,x,height,width)&(1u<<25))>>12);
            }else if(op==1){
                bool safe=y>=12 && y+12<height;
                for(int dy=-12;dy<=12;++dy)safe=safe && ((get(y+dy,x,height,width)>>12)&1);
                int best=0,dir=0,ds[8];
#pragma HLS ARRAY_PARTITION variable=ds complete
                for(int k=0;k<8;++k){
                    int d=0;
                    for(int b=0;b<3;++b){
                        int c=0,l=0,r=0;
                        for(int t=0;t<13;++t){
                            int yy=y+POS[k][t][0],xx=x+POS[k][t][1];
                            int ny=NORMAL[k][b][0],nx=NORMAL[k][b][1];
                            c+=get(yy,xx,height,width)&4095;
                            l+=get(yy+ny,xx+nx,height,width)&4095;
                            r+=get(yy-ny,xx-nx,height,width)&4095;
                        }
                        int v=(l<r?l:r)-c;if(v>d)d=v;
                    }
                    ds[k]=d;if(d>best){best=d;dir=k;}
                }
                if(!safe)best=0;
                int g=get(y,x,height,width)&4095,ny=UNIT[dir][0],nx=UNIT[dir][1];
                bool ridge=g<=int(get(y+ny,x+nx,height,width)&4095)+2 && g<=int(get(y-ny,x-nx,height,width)&4095)+2;
                bool weak=safe && ridge && best>=416 && best-ds[(dir+4)&7]>=208;
                bool strong=weak && best>=832;
                value=uint32_t(best)|(uint32_t(dir)<<16)|(uint32_t(weak)<<19)|(uint32_t(strong)<<20);
            }else if(op==2){value=(get(y,x,height,width)>>20)&1;
            }else if(op==3){
                bool v=false;
                for(int dy=-1;dy<=1;++dy)for(int dx=-1;dx<=1;++dx)v=v || (get(y+dy,x+dx,height,width)&1);
                value=v && ((mem[2*n+y*width+x]>>19)&1);
            }else{
                int support=0;
                for(int dy=-4;dy<=4;++dy)for(int dx=-4;dx<=4;++dx){
                    if(y+dy>=0 && y+dy<height && x+dx>=0 && x+dx<width)support+=get(y+dy,x+dx,height,width)&1;
                }
                bool old=(mem[y*width+x]>>25)&1;
                bool add=(get(y,x,height,width)&1) && support>=8 && !old;
                bool uncertain=((mem[2*n+y*width+x]>>19)&1) && !add && !old;
                value=uint32_t(old||add)|(uint32_t(add)<<1)|(uint32_t(uncertain)<<2);
            }
            mem[dest+y*width+x]=value;
        }
    }
    if(op==0){phase=1;grows=0;}else if(op==1)phase=2;else if(op==2)phase=3;else if(op==3)++grows;else phase=4;
    return 0;
}
