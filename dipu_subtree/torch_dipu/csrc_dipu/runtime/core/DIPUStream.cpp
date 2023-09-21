// Copyright (c) 2023, DeepLink.
#include <array>
#include <atomic>
#include <cstdint>
#include <cstring>
#include <vector>
#include <sys/time.h>
#include <unistd.h>
#include <iostream>

#include <c10/util/Exception.h>

#include "DIPUGuard.h"
#include "DIPUStream.h"

using dipu::devapis::deviceId_t;
namespace dipu {

namespace {
enum class StreamIdType : uint8_t {
  DEFAULT = 0x0,
  POOL = 0x1,
};

std::ostream& operator<<(std::ostream& stream, StreamIdType s) {
  switch (s) {
    case StreamIdType::DEFAULT:
      stream << "DEFAULT";
      break;
    case StreamIdType::POOL:
      stream << "POOL";
      break;
    default:
      stream << static_cast<uint8_t>(s);
      break;
  }
  return stream;
}
// follow old pytorch cuda, seems new version use an opposite strategy.   
static constexpr int kStreamsPerPoolBits = 3;
static constexpr int kStreamsPerPool = 1 << kStreamsPerPoolBits;

// Global stream state and constants
static c10::DeviceIndex num_dipus = -1;
// Default streams
static std::once_flag global_init_flag;

// streamid contains streamtype and/or raw stream id in DIPUStreamDevice pool
static thread_local std::unique_ptr<c10::StreamId[]> current_streams = nullptr;

static c10::StreamId makeC10StreamId(StreamIdType sType, size_t id) {
  return ((uint32_t)static_cast<c10::StreamId>(sType) << kStreamsPerPoolBits) |
    static_cast<c10::StreamId>(id);
}

// manage per-device streams
struct DIPUStreamDevice {
private:
  // Default streams
  std::once_flag pool_flag;
  std::once_flag default_flag;
  deviceId_t devidx_; 
  // seems pytorch 2.0 giveup default stream and enable cuda per_thread stream feature at compile time.
  // it cannot be applied to othe device.
  deviceStream_t default_stream = nullptr;
  
  std::atomic<uint32_t> next_pool_pos;
  std::array<deviceStream_t, kStreamsPerPool> pool_streams;

  inline uint32_t getNextPoolIdx() {
    auto raw_idx = next_pool_pos++;
    return raw_idx % kStreamsPerPool;
  }

  inline StreamIdType getStreamIdType(c10::StreamId s) {
    return static_cast<StreamIdType>((uint32_t)s >> kStreamsPerPoolBits);
  }

  inline size_t getStreamIdIndex(c10::StreamId s) {
    return static_cast<size_t>((uint32_t)s & ((1 << kStreamsPerPoolBits) - 1));
  }
  void _doInitPool() {
    DIPUGuard device_guard{devidx_};
    for (auto i = decltype(kStreamsPerPool){0}; i < kStreamsPerPool; ++i) {
      auto& raw_device_stream = pool_streams[i];
      devproxy::createStream(&raw_device_stream);
    }
  }

  void _doInitDeivce() {
    auto cur_device = devproxy::current_device();
    devproxy::setDevice(devidx_);
    devproxy::createStream(&default_stream);
    devproxy::setDevice(cur_device);
  }

public:
  DIPUStreamDevice(deviceId_t devidx) {
    devidx_ = devidx;
    next_pool_pos = 0;
  }

  DIPUStream getDIPUStreamfromPool() {
    const auto idx = getNextPoolIdx();
    return DIPUStream(devidx_, makeC10StreamId(StreamIdType::POOL, idx));
  }

  DIPUStream getDefaultDIPUStream() {
    return DIPUStream(devidx_, makeC10StreamId(StreamIdType::DEFAULT, 0));
  }

  // c10:StreamId -> rawStream saved in DIPUStreamDevice.
  deviceStream_t obtainRawStream(c10::StreamId stream_id) {
    StreamIdType st = getStreamIdType(stream_id);
    size_t sidx = getStreamIdIndex(stream_id);
    switch (st) {
      case StreamIdType::DEFAULT:
        AT_ASSERTM(
            sidx == 0,
            "Unrecognized stream ",
            stream_id,
            " (I think this should be the default stream, but I got a non-zero index ",
            sidx,
            ").",
            " Did you manufacture the StreamId yourself?  Don't do that; use the",
            " official API like c10::cuda::getStreamFromPool() to get a new stream.");
        return default_stream;
      case StreamIdType::POOL:
        return pool_streams[sidx];
      default:
        AT_ASSERTM(
            0,
            "Unrecognized stream ",
            stream_id,
            " (I didn't recognize the stream type, ",
            st,
            ")");
    }
  }
  void initPool() {
    std::call_once(pool_flag, &DIPUStreamDevice::_doInitPool, this);
  }
  void initDevice() {
    std::call_once(default_flag, &DIPUStreamDevice::_doInitDeivce, this);
  }
};

static std::array<std::unique_ptr<DIPUStreamDevice>, C10_COMPILE_TIME_MAX_DIPUS> streamDeviceList; 

static void initGlobalStreamState() {
  num_dipus = devproxy::getDeviceCount();
  // Check if the number of DIPU matches the expected compile-time max number
  // of DIPU.
  AT_ASSERTM(
      num_dipus <= C10_COMPILE_TIME_MAX_DIPUS,
      "Number of DIPU devices on the machine is larger than the compiled "
      "max number of dipus expected (",
      C10_COMPILE_TIME_MAX_DIPUS,
      "). Increase that and recompile.");

  for (int i=0; i< num_dipus; i++) {
    streamDeviceList[i] = std::move(std::unique_ptr<DIPUStreamDevice>(new DIPUStreamDevice(i)));
  }
}

static c10::DeviceIndex initDIPUGlobal(c10::DeviceIndex devIdx) {
  // Inits default streams (once, globally)
  std::call_once(global_init_flag, initGlobalStreamState);

  // check device id
  if (devIdx == -1) {
    devIdx = devproxy::current_device();
  }
  AT_ASSERT(devIdx >= 0 && devIdx < num_dipus);
  streamDeviceList[devIdx]->initDevice();

  // current_streams is thread local. so check every time.
  if (current_streams) {
    return devIdx;
  }
  current_streams = std::make_unique<c10::StreamId[]>(num_dipus);

  // Inits current streams (thread local) to default streams
  for (const auto i : c10::irange(num_dipus)) {
    current_streams[i] = makeC10StreamId(StreamIdType::DEFAULT, 0);
  }
  // set device default stream in init
  return devIdx;
}

} // end anonymous namespace

// api
deviceStream_t DIPUStream::rawstream() const {
  return streamDeviceList[this->device_index()]->obtainRawStream(this->unwrap().id());
}

DIPUStream getDIPUStreamFromPool(c10::DeviceIndex devIdx) {
  devIdx = initDIPUGlobal(devIdx);
  // Initializes the stream pools (once)
  streamDeviceList[devIdx]->initPool();
  return streamDeviceList[devIdx]->getDIPUStreamfromPool();
}

DIPUStream getDefaultDIPUStream(c10::DeviceIndex devIdx) {
  devIdx = initDIPUGlobal(devIdx);
  return streamDeviceList[devIdx]->getDefaultDIPUStream();
}

DIPUStream getCurrentDIPUStream(c10::DeviceIndex devIdx) {
  devIdx = initDIPUGlobal(devIdx);
  return DIPUStream(devIdx, current_streams[devIdx]); 
}

// copy from pytorch, not verify
DIPUStream getStreamFromExternal(deviceStream_t ext_stream, c10::DeviceIndex device_index) {
  // The stream pointer will be the actual id
  return DIPUStream(device_index, reinterpret_cast<int64_t>(ext_stream));
}

void setCurrentDIPUStream(DIPUStream stream) {
  auto devIdx = stream.device_index();
  initDIPUGlobal(devIdx);
  current_streams[devIdx] = stream.unwrap().id();
}

std::ostream& operator<<(std::ostream& os, const DIPUStream& stream) {
  return os << stream.unwrap();
}

} // namespace dipu
