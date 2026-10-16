#ifndef RETINA_DETECTOR_HLS_HPP
#define RETINA_DETECTOR_HLS_HPP
#include "retina_refined_hls.hpp"
void retina_detector_c5(hls::stream<ap_uint<32> >& source,
                       hls::stream<ap_uint<32> >& result,ap_uint<32> control);
// RQ71: bit5 selects C7, requiring bits3/4; threshold is its direct Q8 score.
void retina_detector_hls(hls::stream<ap_uint<32> >& source,
                        hls::stream<ap_uint<32> >& result,ap_uint<32> control);
#ifndef __SYNTHESIS__
void c7_test_features(const unsigned char* green,int side,int y,int x,int* features);
#endif
#endif
