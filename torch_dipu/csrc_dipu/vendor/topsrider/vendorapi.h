#pragma once

#include <tops_runtime.h>

namespace dipu {

#define DIPU_CALLTOPSRT(Expr)                        \
  {                                                  \
    ::topsError_t ret = Expr;                        \
    if (ret != ::topsSuccess) {                      \
      throw std::runtime_error("dipu device error"); \
    }                                                \
  }

using deviceStream_t = topsStream_t;
#define deviceDefaultStreamLiteral nullptr
using deviceEvent_t = topsEvent_t;
}
