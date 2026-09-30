# Builds amiga-timing, the driver of tools/timing.py, against vAmiga's core.
# setup/Makefile passes VAMIGA_CORE, the path of vAmiga's Core directory,
# and installs the driver into .venv/bin.
cmake_minimum_required(VERSION 3.16)
project(AmigaTiming CXX)
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED True)

add_subdirectory(${VAMIGA_CORE} vacore)
add_executable(amiga-timing driver.cpp)
target_link_libraries(amiga-timing PRIVATE VACore)
install(TARGETS amiga-timing)
