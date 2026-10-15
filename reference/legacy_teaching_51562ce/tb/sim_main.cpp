#include "Vtb_cpu_lab.h"
#include "verilated.h"
#if VM_TRACE
#include "verilated_fst_c.h"
#endif
#include <cstdlib>
#include <cstring>
#include <memory>
#include <iostream>
#include <string>
// Only drives clock/reset. Testbench controls completion, errors and trace caps.
int main(int argc,char**argv) {
    auto context=std::make_unique<VerilatedContext>();
    context->commandArgs(argc,argv);
    unsigned reset_cycles=4;
    std::string wave_path;
    for(int n=1;n<argc;++n) {
        if(std::strncmp(argv[n],"+reset_cycles=",14)==0)
            reset_cycles=unsigned(std::strtoul(argv[n]+14,nullptr,10));
        if(std::strncmp(argv[n],"+wave=",6)==0) wave_path=argv[n]+6;
    }
    if(!reset_cycles) { std::cerr<<"reset_cycles must be >= 1\n"; return 2; }
    if(!wave_path.empty()) context->traceEverOn(true);
    auto top=std::make_unique<Vtb_cpu_lab>(context.get());
#if VM_TRACE
    std::unique_ptr<VerilatedFstC> wave;
    if(!wave_path.empty()) {
        wave=std::make_unique<VerilatedFstC>();
        top->trace(wave.get(),8);
        wave->open(wave_path.c_str());
    }
#else
    if(!wave_path.empty()) { std::cerr<<"Build with --trace-fst for +wave\n"; return 2; }
#endif
    top->clk=0; top->rst_n=0; top->eval();
    uint64_t cycle=0;
    while(!context->gotFinish()) {
        top->clk=0; top->rst_n=(cycle>=reset_cycles); top->eval();
#if VM_TRACE
        if(wave) wave->dump(context->time());
#endif
        context->timeInc(1);
        top->clk=1; top->eval();
#if VM_TRACE
        if(wave) wave->dump(context->time());
#endif
        context->timeInc(1); ++cycle;
    }
    int status=top->exit_code_o;
    top->final();
#if VM_TRACE
    if(wave) wave->close();
#endif
    return status;
}
