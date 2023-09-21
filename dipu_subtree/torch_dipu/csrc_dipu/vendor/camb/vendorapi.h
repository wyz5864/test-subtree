// Copyright (c) 2023, DeepLink.
#pragma once

#include <cnrt.h>
#include <cndev.h>
#include <cnnl.h>
#include <cncl.h>
#include <c10/util/Exception.h>

#include <csrc_dipu/common.h>

namespace dipu {

#define DIPU_CALLCNRT(Expr)                                                         \
    {                                                                               \
        ::cnrtRet_t ret = Expr;                                                     \
        TORCH_CHECK(ret == ::CNRT_RET_SUCCESS, "call cnrt error, expr = ", #Expr, ", ret = ", ret); \
    }

#define DIPU_CALLCNDEV(Expr)                                                         \
    {                                                                                \
        ::cndevRet_t ret = Expr;                                                     \
        TORCH_CHECK(ret == ::CNDEV_SUCCESS, "call cndev error, expr = ", #Expr, ", ret = ", ret); \
    }
  
#define DIPU_CALLCNNL(Expr)                                                         \
    {                                                                               \
        ::cnnlStatus_t ret = Expr;                                                  \
        TORCH_CHECK(ret == ::CNNL_STATUS_SUCCESS, "call cnnl error, expr = ", #Expr, ", ret = ", ret); \
    }


using deviceStream_t = cnrtQueue_t;
#define deviceDefaultStreamLiteral nullptr
using deviceEvent_t = cnrtNotifier_t;
using deviceHandle_t = cnnlHandle_t;

using diclComm_t = cnclComm_t;
using commUniqueId = cnclCliqueId;

}
