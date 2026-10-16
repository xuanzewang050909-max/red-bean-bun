#ifndef RETINA_QUALITY_HLS_HPP
#define RETINA_QUALITY_HLS_HPP
#include "retina_c2_support_hls.hpp"
// Working ABI: stage bits1:0; bit2 side256; bit3 C2; bits15:8 threshold1..255.
// Actual W2 frame-lock/readback and clock observer still require RTL integration.
void retina_quality_hls(hls::stream<ap_uint<32> >& source,
                        hls::stream<ap_uint<32> >& result,ap_uint<32> control);
#endif
