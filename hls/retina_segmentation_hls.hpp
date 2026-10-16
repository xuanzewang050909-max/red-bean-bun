#ifndef RETINA_SEGMENTATION_HLS_HPP
#define RETINA_SEGMENTATION_HLS_HPP
#include "hls_video.h"
#include "hls_stream.h"
#include "ap_int.h"
void retina_segmentation_hls(hls::stream<ap_uint<32> >& source,
                           hls::stream<ap_uint<32> >& result,
                           ap_uint<32> control);
#endif
