#include "retina_refined_hls.hpp"
#include <fstream>
#include <iostream>
#include <cstdio>
int main(){
  std::ifstream config("D:/PLD/retina_fpga/build/q4_refined_vectors_01/csim_cases.txt");
  unsigned index,side,control; unsigned long checked=0; unsigned frames=0;
  if(!config){std::cerr<<"missing cases";return 1;}
  while(config>>index>>side>>control){
    char a[256],b[256];
    sprintf(a,"D:/PLD/retina_fpga/build/q4_refined_vectors_01/case_%02u_input.hex",index);
    sprintf(b,"D:/PLD/retina_fpga/build/q4_refined_vectors_01/case_%02u_expected.hex",index);
    std::ifstream input(a),expected(b); if(!input||!expected)return 2;
    hls::stream<ap_uint<32> > source,result; unsigned word;
    for(unsigned i=0;i<side*side;++i){if(!(input>>std::hex>>word))return 3;source.write(word);}
    retina_refined_hls(source,result,control);
    for(unsigned i=0;i<side*side;++i){if(!(expected>>std::hex>>word)||result.empty())return 4;
      unsigned actual=result.read();if(actual!=word){std::cerr<<"mismatch frame="<<index<<" pixel="<<i<<" got="<<std::hex<<actual<<" expected="<<word<<std::endl;return 5;}++checked;}
    if(!source.empty()||!result.empty())return 6;
    ++frames;std::cout<<"Q4_C5_CSIM_FRAME_PASS "<<index<<" words="<<side*side<<std::endl;
  }
  if(frames!=18)return 7;
  std::cout<<"Q4_C5_CSIM_PASS frames="<<frames<<" words="<<checked<<std::endl;return 0;
}
