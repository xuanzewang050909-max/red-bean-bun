#ifndef RETINA_REFINED_HLS_HPP
#define RETINA_REFINED_HLS_HPP
#include "retina_quality_hls.hpp"
// RQ51: original stage/size/threshold fields; bit3 C2, bit4 C5 refinement.
// C5 requires bit3=1. A and C2 retain their exact original pixel semantics.
void retina_refined_hls(hls::stream<ap_uint<32> >& source,
                        hls::stream<ap_uint<32> >& result, ap_uint<32> control);
void retina_refined_base(hls::stream<ap_uint<32> >& source,
                         hls::stream<ap_uint<32> >& result, ap_uint<32> control);
#endif
