PLATFORM=/mnt/lustre/share/platform
ENV_NAME=dipu_poc
export PATH=`python ${PLATFORM}/env/clear_path.py PATH`
export LD_LIBRARY_PATH=`python ${PLATFORM}/env/clear_path.py LD_LIBRARY_PATH`
GCC_ROOT=/mnt/lustre/share/platform/dep/gcc-7.5
CONDA_ROOT=${PLATFORM}/env/miniconda3.8

export NEUWARE_HOME=/usr/local/neuware
export CC=${GCC_ROOT}/bin/gcc
export CXX=${GCC_ROOT}/bin/g++


export DIOPI_ROOT=$(pwd)/third_party/DIOPI/impl/lib/
export DIPU_ROOT=$(pwd)/torch_dipu
export LIBRARY_PATH=$DIPU_ROOT:${DIOPI_ROOT}:${LIBRARY_PATH}; LD_LIBRARY_PATH=$DIPU_ROOT:$DIOPI_ROOT:$LD_LIBRARY_PATH
export PYTHONPATH=${PYTORCH_DIR}/install_path/lib/python3.8/site-packages:${PYTHONPATH}
export PATH=${PYTORCH_DIR}/install_path/bin:${CONDA_ROOT}/envs/dipu_poc/bin:${CONDA_ROOT}/bin:${PATH}
export LD_PRELOAD=${GCC_ROOT}/lib64/libstdc++.so.6
export PYTHON_INCLUDE_DIR="/mnt/lustre/share/platform/env/miniconda3.8/envs/dipu_poc/include/python3.8"


export NEUWARE_ROOT_DIR=${NEUWARE_HOME}
export VENDOR_INCLUDE_DIRS=${NEUWARE_HOME}/include
export DIOPI_PATH=$(pwd)/third_party/DIOPI/proto
export DIPU_PATH=${DIPU_ROOT}

#export MLU_INVOKE_BLOCKING=1

export DIPU_FORCE_FALLBACK_OPS_LIST=mul.Scalar,mul_.Scalar,mul.Scalar_out,mul_.Tensor,mul.out,add_out,_index_put_impl_,_unique2,col2im

#export DIPU_DEBUG_ALLOCATOR=15
export DIPU_DEVICE_MEMCACHING_ALGORITHM=BS
export DIPU_HOST_MEMCACHING_ALGORITHM=BS


source activate $ENV_NAME

echo  "python path : ${PYTHONPATH}"
