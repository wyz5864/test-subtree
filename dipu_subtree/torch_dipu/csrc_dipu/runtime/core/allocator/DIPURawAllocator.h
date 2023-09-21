// Copyright (c) 2023, DeepLink.
#pragma once

#include <c10/core/Allocator.h>
#include <c10/core/Device.h>

#include <csrc_dipu/common.h>
#include <csrc_dipu/runtime/device/deviceapis.h>
#include <csrc_dipu/runtime/core/MemChecker.h>
#include <iostream>
#include <thread>

namespace dipu {

#define DIPU_DEBUG_ALLOCATOR(mask, x)                                                                                   \
  {                                                                                                                     \
    static int value = []() { auto env = std::getenv("DIPU_DEBUG_ALLOCATOR"); return env ? std::atoi(env) : 0; }();     \
    if ((mask & value) == mask)                                                                                         \
    {                                                                                                                   \
      std::cout << "[" << std::this_thread::get_id() << "]" << x << std::endl;                                          \
    }                                                                                                                   \
  }

class DIPU_API DIPURawDeviceAllocator : public c10::Allocator {
public:
    DIPURawDeviceAllocator();

    virtual c10::DataPtr allocate(size_t size) const;

    c10::DeleterFnPtr raw_deleter() const override;

  private:
    static std::mutex mutex_;
    c10::DataPtr allocate(size_t nbytes, c10::DeviceIndex device_index) const;
  };


class DIPURawHostAllocator : public c10::Allocator {
public:
  c10::DataPtr allocate(size_t size) const;

  c10::DeleterFnPtr raw_deleter() const override;
};

DIPU_API bool isPinnedPtr(const void* ptr);

}  // namespace dipu
