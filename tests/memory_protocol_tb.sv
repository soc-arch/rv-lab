// Independent directed driver: both ports, byte-lane observations, delayed
// responses, response backpressure, error side effects and coherent cold reset.
module memory_protocol_tb;
    logic clk=0,rst_n=0;
    always #5 clk=~clk;
    mem_if imem_if();
    mem_if dmem_if();
    teaching_sram #(.WORDS(128),.REQUIRE_PROGRAM(0)) u_mem(.clk,.rst_n,.imem_if,.dmem_if);
    int checks=0,cycles=0,last_i=-10000000,last_d=-10000000;
    int i_issue=0,d_issue=0;
    bit i_live=0,d_live=0,i_seen=0,d_seen=0;
    string result_file;
    initial begin #200000; $fatal(1,"standalone memory protocol timeout"); end
    always @(posedge clk) begin
        cycles=cycles+1;
        if(!rst_n) begin i_live=0;d_live=0;i_seen=0;d_seen=0;last_i=-10000000;last_d=-10000000; end
        else begin
            if(imem_if.resp_valid) begin
                assert(i_live) else $fatal(1,"unsolicited instruction response");
                if(!i_seen) begin
                    assert(cycles-i_issue==int'(u_mem.i_latency)) else $fatal(1,"incorrect instruction response latency");
                    i_seen=1;
                end
                if(imem_if.resp_ready) i_live=0;
            end
            if(dmem_if.resp_valid) begin
                assert(d_live) else $fatal(1,"unsolicited data response");
                if(!d_seen) begin
                    assert(cycles-d_issue==int'(u_mem.d_latency)) else $fatal(1,"incorrect data response latency");
                    d_seen=1;
                end
                if(dmem_if.resp_ready) d_live=0;
            end
            if(imem_if.req_valid && imem_if.req_ready) begin
                assert(!i_live && cycles-last_i>=int'(u_mem.i_interval)) else $fatal(1,"instruction resource/interval violation");
                i_live=1;i_seen=0;i_issue=cycles;last_i=cycles;
            end
            if(dmem_if.req_valid && dmem_if.req_ready) begin
                assert(!d_live && cycles-last_d>=int'(u_mem.d_interval)) else $fatal(1,"data resource/interval violation");
                d_live=1;d_seen=0;d_issue=cycles;last_d=cycles;
            end
        end
    end
    task automatic check(input bit ok,input string label);
        assert(ok) else $fatal(1,"%s",label);
        checks=checks+1;
    endtask
    task automatic data_access(input logic[31:0] addr,input logic[1:0] size,input bit wr,
            input logic[31:0] data,input logic[3:0] mask,input logic[31:0] expected,
            input bit error,input bit id,input int hold_cycles);
        @(negedge clk);
        dmem_if.req_valid=1; dmem_if.req_addr=addr; dmem_if.req_size=size;
        dmem_if.req_write=wr; dmem_if.req_wdata=data; dmem_if.req_wstrb=mask; dmem_if.req_id=id;
        do @(posedge clk); while(!dmem_if.req_ready);
        @(negedge clk); dmem_if.req_valid=0;
        while(!dmem_if.resp_valid) @(negedge clk);
        repeat(hold_cycles+1) begin
            check(dmem_if.resp_valid && dmem_if.resp_id==id && dmem_if.resp_error==error &&
                  dmem_if.resp_rdata==expected,"data response payload/hold");
            check(!dmem_if.req_ready,"must reserve blocked response slot");
            @(negedge clk);
        end
        dmem_if.resp_ready=1;
        @(negedge clk); dmem_if.resp_ready=0;
        check(!dmem_if.resp_valid,"data response consumed once");
    endtask
    task automatic insn_access(input logic[31:0] addr,input logic[31:0] expected,input bit error,input bit id);
        @(negedge clk); imem_if.req_valid=1; imem_if.req_addr=addr; imem_if.req_id=id;
        do @(posedge clk); while(!imem_if.req_ready);
        @(negedge clk); imem_if.req_valid=0;
        while(!imem_if.resp_valid) @(negedge clk);
        repeat(4) begin
            check(imem_if.resp_valid && imem_if.resp_id==id && imem_if.resp_error==error &&
                  imem_if.resp_rdata==expected,"instruction response payload/hold");
            @(negedge clk);
        end
        imem_if.resp_ready=1;
        @(negedge clk); imem_if.resp_ready=0;
        check(!imem_if.resp_valid,"instruction response consumed once");
    endtask
    initial begin
        imem_if.req_valid=0;imem_if.req_id=0;imem_if.req_addr=0;imem_if.req_write=0;
        imem_if.req_size=2;imem_if.req_wdata=0;imem_if.req_wstrb=0;imem_if.req_memtype=0;imem_if.req_priv=3;imem_if.resp_ready=0;
        dmem_if.req_valid=0;dmem_if.req_id=0;dmem_if.req_addr=0;dmem_if.req_write=0;
        dmem_if.req_size=2;dmem_if.req_wdata=0;dmem_if.req_wstrb=0;dmem_if.req_memtype=0;dmem_if.req_priv=3;dmem_if.resp_ready=0;
        repeat(3) @(negedge clk);rst_n=1;
        data_access(32'h80000000,2,1,32'h44332211,15,0,0,1,5);
        check(u_mem.store_writes==1,"backpressured write executes exactly once");
        data_access(32'h80000000,0,0,0,0,32'h00000011,0,0,1);
        data_access(32'h80000001,0,0,0,0,32'h00002200,0,1,1);
        data_access(32'h80000002,0,0,0,0,32'h00330000,0,0,1);
        data_access(32'h80000003,0,0,0,0,32'h44000000,0,1,1);
        data_access(32'h80000002,1,0,0,0,32'h44330000,0,0,1);
        data_access(32'h80000001,0,1,32'h0000aa00,2,0,0,1,2);
        data_access(32'h80000002,1,1,32'hbeef0000,12,0,0,0,2);
        data_access(32'h80000000,2,0,0,0,32'hbeefaa11,0,1,1);
        fork
            insn_access(32'h80000000,32'hbeefaa11,0,1);
            data_access(32'h80000008,2,1,32'h12345678,15,0,0,0,3);
        join
        insn_access(32'h80000008,32'h12345678,0,0);
        data_access(32'h80000001,2,1,32'hffffffff,15,0,1,1,2);
        data_access(32'h80000200,2,0,0,0,0,1,0,1);
        data_access(32'h80000004,0,1,32'h000000ff,2,0,1,1,1);
        check(u_mem.peek_word(32'h80000000)==32'hbeefaa11,"invalid store must not modify SRAM");
        data_access(32'h80000020,2,1,32'hdeadbeef,15,0,1,0,4);
        check(u_mem.peek_word(32'h80000020)==0,"injected failed store has no side effect");
        data_access(32'h80000020,2,1,32'hcafebabe,15,0,0,1,2);
        data_access(32'h80000020,2,0,0,0,32'hcafebabe,0,0,1);
        insn_access(32'h80000040,0,1,1);
        insn_access(32'h80000200,0,1,0);
        check(u_mem.i_accepted==u_mem.i_completed && u_mem.d_accepted==u_mem.d_completed,"balanced accepted/completed counts");
        check(u_mem.store_writes==5,"only successful stores update SRAM");
        check(u_mem.d_errors==4 && u_mem.i_errors==2,"exact completed error counts");
        check(u_mem.i_response_backpressure>0 && u_mem.d_response_backpressure>0,"both response channels backpressured");
        // Simultaneous service collision: defined old-data result, not FPGA mode inference.
        if(u_mem.stall_max==0 && u_mem.i_latency==u_mem.d_latency) begin
            repeat(10) @(negedge clk);
            fork
                insn_access(32'h80000100,0,0,0);
                data_access(32'h80000100,2,1,32'h5a5aa5a5,15,0,0,0,2);
            join
            insn_access(32'h80000100,32'h5a5aa5a5,0,1);
        end
        // Reset discards a pending response, but cannot roll back a completed write.
        @(negedge clk);dmem_if.req_valid=1;dmem_if.req_addr=32'h80000000;dmem_if.req_size=2;
        dmem_if.req_write=0;dmem_if.req_wstrb=0;
        do @(posedge clk);while(!dmem_if.req_ready);
        @(negedge clk);dmem_if.req_valid=0;rst_n=0;
        repeat(3) @(negedge clk);rst_n=1;
        repeat(8) @(negedge clk);
        check(!imem_if.resp_valid && !dmem_if.resp_valid,"cold reset removes stale responses");
        data_access(32'h80000000,2,0,0,0,32'hbeefaa11,0,0,1);
        if($value$plusargs("result_file=%s",result_file)) begin
            integer fd;
            fd=$fopen(result_file,"w");
            $fwrite(fd,"{\"status\":\"pass\",\"checks\":%0d,\"cycles\":%0d}\n",checks,cycles);
            $fclose(fd);
        end
        $display("[MEMORY-PROTOCOL] PASS checks=%0d cycles=%0d",checks,cycles);
        $finish;
    end
endmodule
