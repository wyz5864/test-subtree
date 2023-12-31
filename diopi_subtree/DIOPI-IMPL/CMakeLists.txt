cmake_minimum_required(VERSION 3.4)
project(diopi_impl)

option(TEST "Whether to compile DIOPI with runtime" OFF)
option(DEBUG "whether to use debug" ON)
option(DYLOAD "Whether to load so in runtime by dlopen" OFF)
include_directories(SYSTEM "${PROJECT_SOURCE_DIR}/proto/include")

if (DEBUG)
    SET(CMAKE_BUILD_TYPE "Debug")
else()
    SET(CMAKE_BUILD_TYPE "Release")
endif()

SET(LIBRARY_OUTPUT_PATH ${PROJECT_SOURCE_DIR}/lib)

add_definitions(-DDIOPI_ATTR_WEAK)

set(DEVICEIMPL diopi_impl)

list(APPEND IMPL_CUDA "CUDA" "cuda")
list(APPEND IMPL_TORCH "TORCH" "LIBTORCH" "ATEN" "PYTORCH" "torch" "libtorch" "aten" "pytorch" "PyTorch")
list(APPEND IMPL_CAMB_TORCH "CAMB_PYTORCH" "camb_pytorch")
list(APPEND IMPL_CAMB "CAMB" "camb")

add_definitions(-std=c++14)

if (${IMPL_OPT} IN_LIST IMPL_CUDA)
    add_subdirectory(cuda)
elseif (${IMPL_OPT} IN_LIST IMPL_TORCH)
    add_subdirectory(torch)
elseif (${IMPL_OPT} IN_LIST IMPL_CAMB_TORCH)
    add_subdirectory(camb_pytorch)
elseif (${IMPL_OPT} IN_LIST IMPL_CAMB)
    add_subdirectory(camb)
elseif (${IMPL_OPT} IN_LIST IMPL_ASCEND)
        add_subdirectory(ascend)
else()
    message(WARNING "No implementation module is compiled, cmake requires option -DIMPL_OPT=CUDA or TORCH")
endif()

