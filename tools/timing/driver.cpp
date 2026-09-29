// Run a boot ROM in vAmiga and report the CPU clock at breakpoints.
//
// Usage: amiga-timing ROM ADDR...
//
// ROM is a 256 KB image; the Amiga boots it as its Kickstart. Each ADDR,
// in hex, is a breakpoint. The run goes on until every breakpoint was hit
// once. For each hit, in the order of the hits, a line "ADDR CYCLES"
// gives the CPU clock in 68000 cycles. tools/timing.py builds this program
// and its ROMs; see its docstring.

#include "VAmiga.h"

#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <iterator>
#include <set>
#include <thread>
#include <vector>

using namespace vamiga;
using namespace std::chrono;

// vAmiga calls a listener without checking for null.
static void ignore(const void *, Message) {}

int main(int argc, char **argv)
{
    if (argc < 3) {
        std::fprintf(stderr, "usage: amiga-timing ROM ADDR...\n");
        return 2;
    }
    std::ifstream file(argv[1], std::ios::binary);
    std::vector<u8> rom((std::istreambuf_iterator<char>(file)), {});
    std::set<u32> pending;
    for (int i = 2; i < argc; i++) pending.insert(u32(std::strtoul(argv[i], nullptr, 16)));

    VAmiga amiga;
    amiga.set(ConfigScheme::A500_OCS_1MB);
    amiga.mem.loadRom(rom.data(), rom.size());
    amiga.launch(nullptr, ignore);
    for (auto addr : pending) amiga.cpu.breakpoints.setAt(addr);
    amiga.powerOn();
    amiga.warpOn(1); // source 0 is vAmiga's own warp setting

    // A breakpoint pauses the emulator. Its message may not reach a
    // listener, so this polls.
    auto deadline = steady_clock::now() + seconds(20);
    while (!pending.empty()) {
        amiga.run();
        std::this_thread::sleep_for(milliseconds(20));
        while (amiga.isRunning()) {
            if (steady_clock::now() > deadline) {
                std::fprintf(stderr, "amiga-timing: timeout\n");
                return 1;
            }
            std::this_thread::sleep_for(milliseconds(5));
        }
        auto info = amiga.cpu.getInfo();
        u32 pc = info.pc0;
        if (pending.erase(pc)) {
            std::printf("%x %lld\n", pc, (long long)info.clock);
            amiga.cpu.breakpoints.removeAt(pc);
        }
    }
    return 0;
}
