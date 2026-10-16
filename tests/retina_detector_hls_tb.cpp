#include "retina_detector_hls.hpp"
#include <fstream>
#include <iostream>
#include <cstdio>
#include <vector>
int main(){
  const char* root="D:/PLD/retina_fpga/build/q4d_detector_vectors_01/";
  std::ifstream config((std::string(root)+"csim_cases.txt").c_str());
  std::ifstream features((std::string(root)+"feature_oracle.txt").c_str());
  unsigned index,side,control; unsigned long checked=0;unsigned frames=0,feature_checks=0;
  if(!config||!features)return 1;
  while(config>>index>>side>>control){
    char a[300],b[300];sprintf(a,"%scase_%02u_input.hex",root,index);sprintf(b,"%scase_%02u_expected.hex",root,index);
    std::ifstream input(a),expected(b);if(!input||!expected)return 2;
    hls::stream<ap_uint<32> > source,result;unsigned word;std::vector<unsigned char> green(side*side);
    for(unsigned i=0;i<side*side;++i){if(!(input>>std::hex>>word))return 3;source.write(word);green[i]=(word>>8)&255;}
    for(unsigned j=0;j<15;++j){unsigned fi,y,x;int wanted,got[36];if(!(features>>fi>>y>>x)||fi!=index)return 9;
      c7_test_features(&green[0],side,y,x,got);
      for(int k=0;k<36;++k){if(!(features>>wanted)||got[k]!=wanted){std::cerr<<"feature mismatch "<<index<<" "<<y<<" "<<x<<" "<<k<<" "<<got[k]<<" "<<wanted<<std::endl;return 10;}++feature_checks;}}
    retina_detector_hls(source,result,control);
    for(unsigned i=0;i<side*side;++i){if(!(expected>>std::hex>>word)||result.empty())return 4;
      unsigned actual=result.read();if(actual!=word){std::cerr<<"mismatch frame="<<index<<" pixel="<<i<<" got="<<std::hex<<actual<<" expected="<<word<<std::endl;return 5;}++checked;}
    if(!source.empty()||!result.empty())return 6;
    ++frames;std::cout<<"C7_CSIM_FRAME_PASS "<<index<<" words="<<side*side<<std::endl;
  }
  if(frames!=18)return 7;
  std::cout<<"C7_CSIM_PASS frames="<<frames<<" words="<<checked<<" features="<<feature_checks<<std::endl;return 0;
}
