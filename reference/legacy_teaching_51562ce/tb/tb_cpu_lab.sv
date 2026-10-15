// Replace the CPU sources, keeping teaching_cpu's public memory/trace boundary.
// Only CPU and dual-port SRAM are instantiated. No CPU hierarchical taps or DPI.
module tb_cpu_lab(input logic clk,rst_n,output logic[7:0] exit_code_o);
    localparam logic[31:0] RAM_BASE=32'h8000_0000;
    localparam int RAM_BYTES=1048576;
    mem_if imem_if();
    mem_if dmem_if();
    logic drain_req=0,drain_done;
    logic [31:0] i_owner_addr=0,d_owner_addr=0,d_owner_pc=0;
    teaching_trace_pkg::cpu_trace_t obs;
    teaching_cpu #(.RESET_PC(RAM_BASE)) u_cpu(
        .clk,.rst_n,.imem_if,.dmem_if,.drain_req_i(drain_req),.drain_done_o(drain_done),
        .irq_software_i(1'b0),.irq_timer_i(1'b0),.irq_external_i(1'b0),
        .commit_valid(),.commit_pc(),.commit_rd(),.commit_rd_data(),
        .commit_rd_we(),.events_o(),.trace_o(obs));
    teaching_sram #(.BASE(RAM_BASE),.WORDS(RAM_BYTES/4)) u_mem(
        .clk,.rst_n,.imem_if,.dmem_if);

    longint unsigned cycles=0,retired=0,timeout_cycles=1000000;
    longint unsigned trace_limit=20000,trace_count=0,trace_eligible_count=0;
    longint unsigned roi_start_cycle=0,roi_start_retired=0,roi_cycles=0,roi_retired=0;
    logic roi_active=0,roi_complete=0,done=0;
    logic[31:0] tohost_addr,signature_begin=0,signature_end=0;
    logic[31:0] roi_begin_addr=0,roi_end_addr=0,trace_start_pc=0;
    logic trace_started=1;
    logic pending_host=0,pending_begin=0,pending_end=0;
    logic[31:0] host_data=0,host_pc=0,begin_pc=0,end_pc=0;
    // Optional software CSR telemetry, separate from the functional signature.
    logic [31:0] perf_addr=0;
    string trace_file,commit_file,dump_file,result_file,perf_file;
    integer trace_fd=0,commit_fd=0;
    int expected_trap_cause=-1;
    logic [31:0] expected_trap_pc=0,expected_trap_value=0;
    bit check_trap_pc=0,check_trap_value=0;
    longint unsigned drain_at=0,drain_start=0,drain_count=0,drain_wait=0;
    int drain_when_i_stalled=0,drain_when_d_stalled=0,drain_hold=3,drain_held=0;
    bit drain_started=0,drain_seen_done=0;


    function automatic string state_name(input logic[7:0] state);
        case(state)
            8'h01:return "IDLE";
            8'h02:return "MEM_REQ";
            8'h04:return "MEM_RESP";
            8'h08:return "MEM_WB";
            8'h10:return "MUL_WAIT";
            8'h20:return "DIV_WAIT";
            8'h40:return "MEM_REQ2";
            8'h80:return "MEM_RESP2";
            default:return "UNKNOWN";
        endcase
    endfunction

    initial begin
        exit_code_o=1;
        if(!$value$plusargs("tohost=%h",tohost_addr)) $fatal(1,"Missing +tohost=<ELF symbol hex address>");
        void'($value$plusargs("timeout=%d",timeout_cycles));
        void'($value$plusargs("expected_trap_cause=%d",expected_trap_cause));
        check_trap_pc=$value$plusargs("expected_trap_pc=%h",expected_trap_pc)!=0;
        check_trap_value=$value$plusargs("expected_trap_value=%h",expected_trap_value)!=0;
        void'($value$plusargs("drain_at=%d",drain_at));
        void'($value$plusargs("drain_when_i_stalled=%d",drain_when_i_stalled));
        void'($value$plusargs("drain_when_d_stalled=%d",drain_when_d_stalled));
        void'($value$plusargs("drain_hold=%d",drain_hold));
        void'($value$plusargs("trace_limit=%d",trace_limit));
        void'($value$plusargs("signature_begin=%h",signature_begin));
        void'($value$plusargs("signature_end=%h",signature_end));
        void'($value$plusargs("roi_begin_addr=%h",roi_begin_addr));
        void'($value$plusargs("roi_end_addr=%h",roi_end_addr));
        void'($value$plusargs("dump_file=%s",dump_file));
        void'($value$plusargs("result_file=%s",result_file));
        void'($value$plusargs("perf_addr=%h",perf_addr));
        void'($value$plusargs("perf_file=%s",perf_file));
        if(perf_file!="") assert(perf_addr>=RAM_BASE && perf_addr<=RAM_BASE+RAM_BYTES-64 && perf_addr[3:0]==0)
            else $fatal(1,"CSR telemetry must be 16 aligned words in SRAM");
        if($value$plusargs("trace_start_pc=%h",trace_start_pc)) trace_started=0;
        if($value$plusargs("trace_file=%s",trace_file)) begin
            trace_fd=$fopen(trace_file,"w");
            if(trace_fd==0) $fatal(1,"Cannot open trace output");
        end
        if($value$plusargs("commit_file=%s",commit_file)) begin
            commit_fd=$fopen(commit_file,"w");
            if(commit_fd==0) $fatal(1,"Cannot open commit output");
        end
        assert(tohost_addr>=RAM_BASE && tohost_addr<RAM_BASE+RAM_BYTES && tohost_addr[2:0]==0)
            else $fatal(1,"tohost must be aligned 64-bit SRAM variable");
        if(signature_end!=0) assert(signature_begin>=RAM_BASE && signature_end<=RAM_BASE+RAM_BYTES &&
            signature_end>=signature_begin && signature_begin[1:0]==0 && signature_end[1:0]==0)
            else $fatal(1,"Invalid signature range");
    end

    task automatic write_trace;
        $fwrite(trace_fd,"{\"schema_version\":2,\"cycle\":%0d,",cycles);
        $fwrite(trace_fd,"\"fetch\":{\"pc\":%0d,\"insn\":%0d,\"valid\":%0d,\"accepted\":%0d,\"request_pc\":%0d},",
            obs.fetch_pc,obs.fetch_insn,obs.fetch_valid,obs.fetch_accepted,obs.fetch_request_pc);
        $fwrite(trace_fd,"\"execute\":{\"pc\":%0d,\"insn\":%0d,\"valid\":%0d,\"state\":\"%s\",\"state_code\":%0d},",
            obs.execute_pc,obs.execute_insn,obs.execute_valid,state_name(obs.execute_state),obs.execute_state);
        $fwrite(trace_fd,"\"stages\":{\"fetch\":%0d,\"decode\":%0d,\"execute\":%0d,\"memory\":%0d,\"writeback\":%0d},",
            obs.stage_fetch,obs.stage_decode,obs.stage_execute,obs.stage_memory,obs.stage_writeback);
        $fwrite(trace_fd,"\"units\":{\"alu\":%0d,\"branch\":%0d,\"mul\":%0d,\"div\":%0d,\"lsu\":%0d},",
            obs.unit_alu,obs.unit_branch,obs.unit_mul,obs.unit_div,obs.unit_lsu);
        $fwrite(trace_fd,"\"regs\":{\"rs1\":%0d,\"rs2\":%0d,\"rs1_used\":%0d,\"rs2_used\":%0d,\"rs1_value\":%0d,\"rs2_value\":%0d,\"rd\":%0d,\"wb_value\":%0d,\"wb_enable\":%0d},",
            obs.rs1,obs.rs2,obs.rs1_used,obs.rs2_used,obs.rs1_value,obs.rs2_value,obs.rd,obs.wb_value,obs.wb_enable);
        $fwrite(trace_fd,"\"memory\":{\"pc\":%0d,\"valid\":%0d,\"write\":%0d,\"addr\":%0d,\"data\":%0d,\"wstrb\":%0d,\"read_data\":%0d,\"response_valid\":%0d},",
            obs.memory_pc,obs.memory_valid,obs.memory_write,obs.memory_addr,obs.memory_data,obs.memory_wstrb,obs.memory_read_data,obs.memory_response_valid);
        $fwrite(trace_fd,"\"commit\":{\"valid\":%0d,\"pc\":%0d,\"insn\":%0d,\"rd\":%0d,\"rd_data\":%0d,\"rd_we\":%0d},",
            obs.commit_valid,obs.commit_pc,obs.commit_insn,obs.commit_rd,obs.commit_rd_data,obs.commit_rd_we);
        write_port_trace();
        $fwrite(trace_fd,"\"redirect\":{\"valid\":%0d,\"pc\":%0d},\"trap\":{\"valid\":%0d,\"cause\":%0d,\"pc\":%0d,\"value\":%0d}}\n",
            obs.redirect_valid,obs.redirect_pc,obs.trap_valid,obs.trap_cause,obs.trap_pc,obs.trap_value);
    endtask

    task automatic write_port_trace;
        $fwrite(trace_fd,"\"ports\":{\"instruction\":{");
        $fwrite(trace_fd,"\"req_valid\":%0d,\"req_ready\":%0d,\"req_accepted\":%0d,\"req_id\":%0d,\"req_addr\":%0d,\"req_write\":%0d,\"req_size\":%0d,\"req_wdata\":%0d,\"req_wstrb\":%0d,\"req_memtype\":%0d,\"req_priv\":%0d,",
            imem_if.req_valid,imem_if.req_ready,imem_if.req_valid&&imem_if.req_ready,imem_if.req_id,imem_if.req_addr,
            imem_if.req_write,imem_if.req_size,imem_if.req_wdata,imem_if.req_wstrb,imem_if.req_memtype,imem_if.req_priv);
        $fwrite(trace_fd,"\"resp_valid\":%0d,\"resp_ready\":%0d,\"resp_accepted\":%0d,\"resp_id\":%0d,\"resp_rdata\":%0d,\"resp_error\":%0d,\"owner_pc\":%0d,\"owner_addr\":%0d},\"data\":{",
            imem_if.resp_valid,imem_if.resp_ready,imem_if.resp_valid&&imem_if.resp_ready,imem_if.resp_id,
            imem_if.resp_rdata,imem_if.resp_error,i_owner_addr,i_owner_addr);
        $fwrite(trace_fd,"\"req_valid\":%0d,\"req_ready\":%0d,\"req_accepted\":%0d,\"req_id\":%0d,\"req_addr\":%0d,\"req_write\":%0d,\"req_size\":%0d,\"req_wdata\":%0d,\"req_wstrb\":%0d,\"req_memtype\":%0d,\"req_priv\":%0d,",
            dmem_if.req_valid,dmem_if.req_ready,dmem_if.req_valid&&dmem_if.req_ready,dmem_if.req_id,dmem_if.req_addr,
            dmem_if.req_write,dmem_if.req_size,dmem_if.req_wdata,dmem_if.req_wstrb,dmem_if.req_memtype,dmem_if.req_priv);
        $fwrite(trace_fd,"\"resp_valid\":%0d,\"resp_ready\":%0d,\"resp_accepted\":%0d,\"resp_id\":%0d,\"resp_rdata\":%0d,\"resp_error\":%0d,\"owner_pc\":%0d,\"owner_addr\":%0d}},",
            dmem_if.resp_valid,dmem_if.resp_ready,dmem_if.resp_valid&&dmem_if.resp_ready,dmem_if.resp_id,
            dmem_if.resp_rdata,dmem_if.resp_error,d_owner_pc,d_owner_addr);
        $fwrite(trace_fd,"\"drain\":{\"requested\":%0d,\"done\":%0d},",drain_req,drain_done);
    endtask

    task automatic finish_run(input string status,input string reason,input int code);
        integer fd;
        if (!done) begin
        done=1;
        if(perf_file!="") begin
            fd=$fopen(perf_file,"w");
            if(fd==0) $fatal(1,"Cannot open CSR telemetry output");
            for(int word_index=0;word_index<16;word_index++)
                $fwrite(fd,"%08x\n",u_mem.peek_word(perf_addr+32'(word_index*4)));
            $fclose(fd);
        end
        if(dump_file!="") begin
            fd=$fopen(dump_file,"w");
            if(fd==0) $fatal(1,"Cannot open signature output");
            for(logic[31:0] addr=signature_begin;addr<signature_end;addr+=4)
                $fwrite(fd,"%08x\n",u_mem.peek_word(addr));
            $fclose(fd);
        end
        if(result_file!="") begin
            fd=$fopen(result_file,"w");
            if(fd==0) $fatal(1,"Cannot open result output");
            $fwrite(fd,"{\"schema_version\":2,\"backend\":\"rtl\",\"status\":\"%s\",\"reason\":\"%s\",\"cycles\":%0d,\"retired\":%0d,\"tohost\":%0d,\"roi_cycles\":%0d,\"roi_retired\":%0d,\"roi_complete\":%0d,\"roi_start_cycle\":%0d,\"roi_end_cycle\":%0d,\"trace_cycles\":%0d,\"trace_truncated\":%0d,\"trap_cause\":%0d,\"trap_pc\":%0d,\"trap_value\":%0d,",
                status,reason,cycles,retired,host_data,roi_cycles,roi_retired,roi_complete,roi_start_cycle,
                (roi_complete ? roi_start_cycle+roi_cycles : 0),trace_count,
                (trace_fd!=0 && trace_eligible_count>trace_count),obs.trap_cause,obs.trap_pc,obs.trap_value);
            $fwrite(fd,"\"memory_config\":{\"i_latency\":%0d,\"d_latency\":%0d,\"i_interval\":%0d,\"d_interval\":%0d,\"stall_seed\":%0d,\"stall_max\":%0d},",
                u_mem.i_latency,u_mem.d_latency,u_mem.i_interval,u_mem.d_interval,u_mem.stall_seed,u_mem.stall_max);
            $fwrite(fd,"\"memory_counts\":{\"i_accepted\":%0d,\"d_accepted\":%0d,\"i_completed\":%0d,\"d_completed\":%0d,\"i_errors\":%0d,\"d_errors\":%0d,\"store_writes\":%0d,",
                u_mem.i_accepted+64'(imem_if.req_valid&&imem_if.req_ready),u_mem.d_accepted+64'(dmem_if.req_valid&&dmem_if.req_ready),
                u_mem.i_completed+64'(imem_if.resp_valid&&imem_if.resp_ready),u_mem.d_completed+64'(dmem_if.resp_valid&&dmem_if.resp_ready),
                u_mem.i_errors+64'(imem_if.resp_valid&&imem_if.resp_ready&&imem_if.resp_error),
                u_mem.d_errors+64'(dmem_if.resp_valid&&dmem_if.resp_ready&&dmem_if.resp_error),u_mem.store_writes);
            $fwrite(fd,"\"i_request_wait\":%0d,\"d_request_wait\":%0d,\"i_response_wait\":%0d,\"d_response_wait\":%0d,\"i_response_backpressure\":%0d,\"d_response_backpressure\":%0d},\"drain_count\":%0d,\"drain_wait_cycles\":%0d}\n",
                u_mem.i_request_wait+64'(imem_if.req_valid&&!imem_if.req_ready),
                u_mem.d_request_wait+64'(dmem_if.req_valid&&!dmem_if.req_ready),
                u_mem.i_response_wait+64'(u_mem.i_busy&&!imem_if.resp_valid),
                u_mem.d_response_wait+64'(u_mem.d_busy&&!dmem_if.resp_valid),
                u_mem.i_response_backpressure+64'(imem_if.resp_valid&&!imem_if.resp_ready),
                u_mem.d_response_backpressure+64'(dmem_if.resp_valid&&!dmem_if.resp_ready),drain_count,drain_wait);
            $fclose(fd);
        end
        if(trace_fd!=0) $fclose(trace_fd);
        if(commit_fd!=0) $fclose(commit_fd);
        exit_code_o=8'(code);
        $display("[CPU-LAB] %s reason=%s cycles=%0d retired=%0d roi_cycles=%0d",status,reason,cycles,retired,roi_cycles);
        $finish;
        end
    endtask

    // Samples describe actions at this edge, BEFORE register/SRAM NBA updates.
    always @(posedge clk) if(rst_n && !done) begin
        cycles=cycles+1;
        if(!trace_started && obs.execute_valid && obs.execute_pc==trace_start_pc) trace_started=1;
        if(trace_fd!=0 && trace_started) begin
            trace_eligible_count=trace_eligible_count+1;
            if(trace_count<trace_limit) begin write_trace(); trace_count=trace_count+1; end
        end
        if(obs.commit_valid) begin
            retired=retired+1;
            if(commit_fd!=0) $fwrite(commit_fd,
                "{\"cycle\":%0d,\"pc\":%0d,\"insn\":%0d,\"rd\":%0d,\"rd_data\":%0d,\"rd_we\":%0d}\n",
                cycles,obs.commit_pc,obs.commit_insn,obs.commit_rd,obs.commit_rd_data,obs.commit_rd_we);
        end
        if(imem_if.req_valid && imem_if.req_ready) i_owner_addr=imem_if.req_addr;
        if(dmem_if.req_valid && dmem_if.req_ready) begin d_owner_addr=dmem_if.req_addr; d_owner_pc=obs.memory_pc; end
        if(!drain_started && ((drain_at!=0 && cycles>=drain_at) ||
           (drain_when_i_stalled!=0 && imem_if.req_valid && !imem_if.req_ready) ||
           (drain_when_d_stalled!=0 && dmem_if.req_valid && !dmem_if.req_ready))) begin
            drain_req<=1; drain_started=1; drain_start=cycles;
        end
        if(drain_req && drain_done) begin
            if(!drain_seen_done) begin
                drain_seen_done=1; drain_count=drain_count+1; drain_wait=cycles-drain_start;
            end
            drain_held=drain_held+1;
            if(drain_held>=drain_hold) drain_req<=0;
        end
        if(obs.trap_valid) begin
            if(expected_trap_cause>=0 && obs.trap_cause==32'(expected_trap_cause) &&
               (!check_trap_pc || obs.trap_pc==expected_trap_pc) &&
               (!check_trap_value || obs.trap_value==expected_trap_value)) finish_run("pass","expected_trap",0);
            else finish_run("fail","unexpected_trap",1);
        end
        else begin
            if(dmem_if.req_valid && dmem_if.req_ready && dmem_if.req_write) begin
                if(dmem_if.req_addr==tohost_addr) begin
                    if(dmem_if.req_wstrb!=4'hf) finish_run("fail","partial_tohost_store",1);
                    else begin pending_host=1; host_data=dmem_if.req_wdata; host_pc=obs.memory_pc; end
                end
                if(roi_begin_addr!=0 && dmem_if.req_addr==roi_begin_addr && dmem_if.req_wdata==1) begin
                    if(dmem_if.req_wstrb!=4'hf || roi_active) finish_run("fail","invalid_roi_begin",1);
                    else begin pending_begin=1; begin_pc=obs.memory_pc; end
                end
                if(roi_end_addr!=0 && dmem_if.req_addr==roi_end_addr && dmem_if.req_wdata==1) begin
                    if(dmem_if.req_wstrb!=4'hf) finish_run("fail","partial_roi_end",1);
                    else begin pending_end=1; end_pc=obs.memory_pc; end
                end
            end
            // Commit-to-commit ROI excludes begin store, includes end store.
            if(pending_begin && obs.commit_valid && obs.commit_pc==begin_pc) begin
                roi_start_cycle=cycles; roi_start_retired=retired;
                roi_active=1; roi_complete=0; pending_begin=0;
            end
            if(pending_end && obs.commit_valid && obs.commit_pc==end_pc) begin
                if(!roi_active) finish_run("fail","roi_end_without_begin",1);
                else begin
                    roi_cycles=cycles-roi_start_cycle; roi_retired=retired-roi_start_retired;
                    roi_active=0; roi_complete=1; pending_end=0;
                end
            end
            if(pending_host && obs.commit_valid && obs.commit_pc==host_pc) begin
                pending_host=0;
                if(host_data[0]) begin
                    if(host_data==1 && expected_trap_cause<0) finish_run("pass","tohost",0);
                    else if(host_data==1) finish_run("fail","expected_trap_missing",1);
                    else finish_run("fail","tohost",1);
                end
            end
            if(cycles>=timeout_cycles) finish_run("timeout","cycle_budget",2);

        end
    end
endmodule
