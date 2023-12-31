/**
 * @file
 * @author DeepLink
 * @copyright  (c) 2023, DeepLink.
 */

#include <diopi/functions.h>

#include "../cnnl_helper.hpp"
#include "../common/common.hpp"

namespace impl {
namespace camb {
extern "C" {

DIOPI_API diopiError_t diopiDiv(diopiContextHandle_t ctx, diopiTensorHandle_t out, diopiConstTensorHandle_t input, diopiConstTensorHandle_t other,
                                diopiRoundMode_t rounding_mode) {
    cnnlHandle_t handle = cnnlHandlePool.get(ctx);
    DiopiTensor input_tensor(input);
    DiopiTensor other_tensor(other);
    DiopiTensor out_tensor(out);

    DiopiTensor out_tensor_temp = out_tensor;
    if ((out_tensor.dtype() != diopi_dtype_float16) && (out_tensor.dtype() != diopi_dtype_float32)) {
        DIOPI_CALL(dataTypeCast(ctx, out_tensor_temp, diopi_dtype_float32));
    } else {
        out_tensor_temp = DiopiTensor(out);
    }

    DIOPI_CALL(dataTypeCast(ctx, input_tensor, out_tensor_temp.dtype()));
    DIOPI_CALL(dataTypeCast(ctx, other_tensor, out_tensor_temp.dtype()));

    CnnlTensorDesc input_desc(input_tensor, CNNL_LAYOUT_ARRAY);
    CnnlTensorDesc other_desc(other_tensor, CNNL_LAYOUT_ARRAY);
    CnnlTensorDesc out_desc(out_tensor_temp, CNNL_LAYOUT_ARRAY);
    size_t workspace_size = 0;
    DIOPI_CALLCNNL(cnnlGetDivWorkspaceSize(handle, input_desc.get(), other_desc.get(), out_desc.get(), &workspace_size));
    void* workspace = nullptr;
    workspace = requiresBuffer(ctx, workspace_size).data();

    cnnlDiv_v2(handle,
               CNNL_COMPUTATION_HIGH_PRECISION,
               input_desc.get(),
               input_tensor.data(),
               other_desc.get(),
               other_tensor.data(),
               workspace,
               workspace_size,
               out_desc.get(),
               out_tensor_temp.data());
    if (out_tensor_temp.dtype() != out_tensor.dtype()) {
        DIOPI_CALL(dataTypeCast(ctx, out_tensor, out_tensor_temp));
    }
    return diopiSuccess;
}

DIOPI_API diopiError_t diopiDivInp(diopiContextHandle_t ctx, diopiTensorHandle_t input, diopiConstTensorHandle_t other, diopiRoundMode_t rounding_mode) {
    DIOPI_CALL(diopiDiv(ctx, input, input, other, rounding_mode));
    return diopiSuccess;
}

DIOPI_API diopiError_t diopiDivScalar(diopiContextHandle_t ctx, diopiTensorHandle_t out, diopiConstTensorHandle_t input, const diopiScalar_t* other,
                                      diopiRoundMode_t rounding_mode) {
    cnnlHandle_t handle = cnnlHandlePool.get(ctx);
    DiopiTensor input_tensor(input);
    DiopiTensor other_tensor_tmp;
    DIOPI_CALL(makeTensorFromScalar(ctx, other, other_tensor_tmp));
    auto other_tensor = other_tensor_tmp.tensorHandle();
    DiopiTensor out_tensor(out);
    DIOPI_CALL(diopiDiv(ctx, out, input, diopiTensorHandle_t(other_tensor), rounding_mode));
    return diopiSuccess;
}
DIOPI_API diopiError_t diopiDivInpScalar(diopiContextHandle_t ctx, diopiTensorHandle_t input, const diopiScalar_t* other, diopiRoundMode_t rounding_mode) {
    DIOPI_CALL(diopiDivScalar(ctx, input, input, other, rounding_mode));
    return diopiSuccess;
}

}  // extern "C"
}  // namespace camb
}  // namespace impl
