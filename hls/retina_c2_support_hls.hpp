#ifndef RETINA_C2_SUPPORT_HLS_HPP
#define RETINA_C2_SUPPORT_HLS_HPP
#include "hls_video.h"
#include "hls_stream.h"
#include "ap_int.h"

// Q2 feasibility probe only. This is not the production overlay ABI.
// Input bytes: enhanced E / original response A / opaque 16-bit alignment tag.
// Output bytes: softened response R / support 0 or 1 / unchanged tag.
void retina_c2_support_hls(hls::stream<ap_uint<32> >& source,
                           hls::stream<ap_uint<32> >& result,
                           ap_uint<32> side);

typedef hls::Mat<512,512,HLS_8UC1> C2Image;
void retina_c2_support(C2Image& enhanced, C2Image& supported);

#endif
