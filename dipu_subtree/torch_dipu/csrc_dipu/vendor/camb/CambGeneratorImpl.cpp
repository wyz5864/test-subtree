// Copyright (c) 2023, DeepLink.
#include <ATen/Utils.h>
#include <ATen/Functions.h>

#include <csrc_dipu/runtime/device/deviceapis.h>
#include <csrc_dipu/runtime/core/DIPUGeneratorImpl.h>
#include <csrc_dipu/runtime/core/DIPUGuard.h>

#include <cnnl.h>

namespace dipu {

static deviceHandle_t getDeviceHandler(c10::DeviceIndex device_index) {
  if (device_index == -1) {
    device_index = devapis::current_device();
  }
  deviceHandle_t handle;
  cnnlCreate(&handle);
  auto stream = getCurrentDIPUStream(device_index);
  cnnlSetQueue(handle, stream.rawstream());
  return handle;
}
  
// Discriminate floating device type.
static bool is_floating_device = true;

class MLUGeneratorImpl : public dipu::DIPUGeneratorImpl {
protected:
  mutable std::once_flag init_state_flag;
public:
  MLUGeneratorImpl(at::DeviceIndex device_index): dipu::DIPUGeneratorImpl(device_index) {
  }
  /**
   * get_init_state_flag
   *
   * See Note [Acquire lock when using random generators]
   */
  void init_state() const override {
    // resize and set the state tensor.
    if (is_floating_device) {
        // std::lock_guard<std::mutex> lock(mutex_);
        std::call_once(init_state_flag, [&] {
        size_t state_size = 0;
        DIPU_CALLCNNL(cnnlRandGetMTGP32StateSize(nullptr, &state_size));
        auto options = at::TensorOptions().device(device_).dtype(at::kByte);
        state_ = at::empty(state_size, options);
        });
    }
  }

  /**
  * set state
  *
  * See Note [Acquire lock when using random generators]
  */
  void set_state(const c10::TensorImpl& state) override {
    at::detail::check_rng_state(state);
    // 5056 is numel() of a cpu state tensor, 816 is gpu's and 1049600 is mlu's,
    // hardcoding the number just like the original impl.
    const int cpu_numel = 5056;
    const int gpu_numel = 816;
    const int mlu_numel = 1049600;
    at::Tensor state_tmp(state.shallow_copy_and_detach(state.version_counter(), true));
    if (state_tmp.numel() == cpu_numel || state_tmp.numel() == gpu_numel) {
        return;
    } else if (state_tmp.numel() == mlu_numel) {
        init_state();
        state_ = state_tmp.to(state_.device());
        state_need_reset_ = false;
    } else {
        TORCH_CHECK(false, "RNG state is wrong size.");
    }
  }

  /**
   * update_state
   *
   * See Note [Acquire lock when using random generators]
    */
  void update_state() const override {
    // update the state tensor.
    if (is_floating_device && state_need_reset_) {
      // ??not use cnnltype convert as torch_mlu?? in observation
      auto state_ptr = state_.tensor_data().data_ptr();
      TORCH_CHECK(state_ptr, "the state point is nullptr, "
                            "please init state before calling its point");
      dipu::DIPUGuard guard(state_.device());
      auto handle = getDeviceHandler(state_.device().index());
      DIPU_CALLCNNL(cnnlRandMakeMTGP32KernelState(handle, state_ptr, nullptr, nullptr, seed_));
      state_need_reset_ = false;
    }
  }
};

const at::Generator vendorMakeGenerator(at::DeviceIndex device_index) {
  return at::make_generator<MLUGeneratorImpl>(device_index);
}

}  // namespace torch_dipu