// Copyright (c) 2023, DeepLink.
#pragma once

#include <c10/core/DeviceGuard.h>
#include <c10/core/StreamGuard.h>
#include <cstddef>

#include "./guardimpl/DIPUGuardImpl.h"


namespace dipu {

using c10::DeviceGuard;

class DIPUGuard: public DeviceGuard {
  public:
    explicit DIPUGuard() = delete;

    explicit DIPUGuard(c10::Device device) : DeviceGuard(device) {}

    explicit DIPUGuard(c10::DeviceIndex device_index) 
      : DeviceGuard(c10::Device(dipu::DIPU_DEVICE_TYPE, device_index)) {}
};

// add necessary func if needed
using OptionalDIPUGuard = c10::OptionalDeviceGuard;
using DIPUStreamGuard = c10::StreamGuard;
using OptionalDIPUStreamGuard = c10::OptionalStreamGuard;

} // namespace dipu