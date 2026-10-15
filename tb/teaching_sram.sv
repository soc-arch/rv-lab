// =============================================================================
// HY-RV | teaching_sram
// Description: Behavioral shared SRAM adapter supporting same-edge completion and reuse.
//
// Purpose: Computer architecture and RTL design education and lab exercises.
// Maintained by: DSAL (Digital System Architecture Lab), Hanyang University
// Website: https://dsa.hanyang.ac.kr
// Supervisor: Prof. Ji-Hoon Kim (jhoonkim@hanyang.ac.kr)
//
// AI tools such as Codex or Claude may have assisted in creating or modifying
// this file. See the applicable manifests and verification records for
// file-specific provenance, revision history, and validation evidence.
// Preserve existing license, copyright, and original author notices.
// =============================================================================

// Explicit II=1 private overlay of the frozen Lab blocking memory-v1 SRAM.
// Completion and replacement may share one edge; acceptance has state priority.
// The producer still holds its response until ready and never cancels requests.
// One reserved response slot per physical port. Array access occurs when service
// finishes; same-edge reads see OLD data. Latency and issue interval are distinct.
module teaching_sram #(
    parameter logic [31:0] BASE=32'h8000_0000,
    parameter int WORDS=262144,
    parameter bit REQUIRE_PROGRAM=1
) (input logic clk,rst_n, mem_if.slave imem_if,dmem_if);
    logic [31:0] mem[0:WORDS-1];
    logic [7:0] image_bytes[0:WORDS*4-1];
    string program_file;
    int unsigned i_latency=1,d_latency=1,i_interval=1,d_interval=1;
    int unsigned stall_seed=1,stall_max=0;
    logic [31:0] i_error_addr=0,d_error_addr=0;
    bit i_error_enabled=0,d_error_enabled=0;
    int d_error_write=-1,error_once=0;
    bit i_injected=0,d_injected=0;
    logic i_busy=0,d_busy=0;
    logic [31:0] i_addr_q,d_addr_q,d_data_q;
    logic [3:0] d_mask_q;
    logic [1:0] d_size_q;
    logic i_id_q,d_id_q,d_write_q,i_error_q,d_error_q;
    int unsigned i_left=0,d_left=0,i_gap=0,d_gap=0,i_stall=0,d_stall=0;
    logic [31:0] i_rng,d_rng;
    longint unsigned i_accepted=0,d_accepted=0,i_completed=0,d_completed=0;
    longint unsigned i_errors=0,d_errors=0,store_writes=0;
    longint unsigned i_request_wait=0,d_request_wait=0,i_response_wait=0,d_response_wait=0;
    longint unsigned i_response_backpressure=0,d_response_backpressure=0;
    wire i_accept=imem_if.req_valid && imem_if.req_ready;
    wire d_accept=dmem_if.req_valid && dmem_if.req_ready;
    wire i_serve=(i_accept && i_latency==1)||(i_busy && !imem_if.resp_valid && i_left==1);
    wire d_serve=(d_accept && d_latency==1)||(d_busy && !dmem_if.resp_valid && d_left==1);
    logic i_bad,d_bad;

    function automatic logic [31:0] next_random(input logic [31:0] x);
        logic [31:0] y;
        y=x^(x<<13); y=y^(y>>17); y=y^(y<<5); return y;
    endfunction
    function automatic logic [3:0] lane_mask(input logic [31:0] addr,input logic[1:0] size);
        if(size>2) return 0;
        return 4'(((1<<(1<<size))-1)<<(addr&3));
    endfunction
    function automatic bit request_ok(input logic[31:0] addr,input logic[1:0] size,
            input logic wr,input logic[3:0] mask,input bit instruction,
            input logic[1:0] memtype,input logic[1:0] priv);
        if(size>2 || memtype==3 || priv==2) return 0;
        if(addr<BASE || (addr-BASE)>=32'(WORDS*4)) return 0;
        if((addr & ((1<<size)-1))!=0 || ((addr&3)+(1<<size))>4) return 0;
        if(wr ? mask!=lane_mask(addr,size) : mask!=0) return 0;
        if(instruction && (wr || size!=2 || memtype==2)) return 0;
        return 1;
    endfunction
    function automatic logic [31:0] read_lanes(input logic[31:0] addr,input logic[1:0] size);
        logic[31:0] value;
        logic[3:0] mask;
        value=0; mask=lane_mask(addr,size);
        for(int b=0;b<4;b++) if(mask[b]) value[8*b+:8]=mem[(addr-BASE)>>2][8*b+:8];
        return value;
    endfunction
    always_comb begin
        i_bad=!request_ok(imem_if.req_addr,imem_if.req_size,imem_if.req_write,
            imem_if.req_wstrb,1,imem_if.req_memtype,imem_if.req_priv) ||
            (i_error_enabled && imem_if.req_addr==i_error_addr && (error_once==0 || !i_injected));
        d_bad=!request_ok(dmem_if.req_addr,dmem_if.req_size,dmem_if.req_write,
            dmem_if.req_wstrb,0,dmem_if.req_memtype,dmem_if.req_priv) ||
            (d_error_enabled && dmem_if.req_addr==d_error_addr &&
            (d_error_write<0 || d_error_write==int'(dmem_if.req_write)) && (error_once==0 || !d_injected));
    end
    initial begin
        void'($value$plusargs("i_latency=%d",i_latency));
        void'($value$plusargs("d_latency=%d",d_latency));
        void'($value$plusargs("i_interval=%d",i_interval));
        void'($value$plusargs("d_interval=%d",d_interval));
        void'($value$plusargs("stall_seed=%d",stall_seed));
        void'($value$plusargs("stall_max=%d",stall_max));
        i_error_enabled=$value$plusargs("i_error_addr=%h",i_error_addr)!=0;
        d_error_enabled=$value$plusargs("d_error_addr=%h",d_error_addr)!=0;
        void'($value$plusargs("d_error_write=%d",d_error_write));
        void'($value$plusargs("error_once=%d",error_once));
        assert(i_latency>=1 && d_latency>=1 && i_interval>=1 && d_interval>=1 &&
               i_latency<=1000000 && d_latency<=1000000 && i_interval<=1000000 && d_interval<=1000000 &&
               stall_max<=1000000 && d_error_write>=-1 && d_error_write<=1)
            else $fatal(1,"Invalid memory timing/error configuration");
        $display("[MEMORY-V1] i_latency=%0d d_latency=%0d i_interval=%0d d_interval=%0d stall_seed=%0d stall_max=%0d",
                 i_latency,d_latency,i_interval,d_interval,stall_seed,stall_max);
        for (int n=0;n<WORDS*4;n++) image_bytes[n]=0;
        if($value$plusargs("program=%s",program_file)) $readmemh(program_file,image_bytes);
        else if(REQUIRE_PROGRAM) $fatal(1,"Missing +program=<relative byte hex>");
        for (int n=0;n<WORDS;n++) mem[n]={image_bytes[4*n+3],image_bytes[4*n+2],image_bytes[4*n+1],image_bytes[4*n]};
    end
    assign imem_if.req_ready=rst_n && (!i_busy || (imem_if.resp_valid && imem_if.resp_ready)) && i_gap==0 && i_stall==0;
    assign dmem_if.req_ready=rst_n && (!d_busy || (dmem_if.resp_valid && dmem_if.resp_ready)) && d_gap==0 && d_stall==0;
    always_ff @(posedge clk or negedge rst_n) begin
        if(!rst_n) begin
            i_busy<=0; d_busy<=0; i_left<=0; d_left<=0; i_gap<=0; d_gap<=0;
            i_rng<=stall_seed==0 ? 32'h13579bdf : stall_seed;
            d_rng<=(stall_seed==0 ? 32'h13579bdf : stall_seed)^32'h9e3779b9;
            i_stall<=stall_seed%(stall_max+1);
            d_stall<=(stall_seed^32'h9e3779b9)%(stall_max+1);
            i_injected<=0; d_injected<=0;
            imem_if.resp_valid<=0; imem_if.resp_id<=0; imem_if.resp_rdata<=0; imem_if.resp_error<=0;
            dmem_if.resp_valid<=0; dmem_if.resp_id<=0; dmem_if.resp_rdata<=0; dmem_if.resp_error<=0;
            i_accepted<=0; d_accepted<=0; i_completed<=0; d_completed<=0;
            i_errors<=0; d_errors<=0; store_writes<=0;
            i_request_wait<=0; d_request_wait<=0; i_response_wait<=0; d_response_wait<=0;
            i_response_backpressure<=0; d_response_backpressure<=0;
        end else begin
            if(i_gap!=0) i_gap<=i_gap-1;
            if(d_gap!=0) d_gap<=d_gap-1;
            if(i_stall!=0) i_stall<=i_stall-1;
            if(d_stall!=0) d_stall<=d_stall-1;
            if(imem_if.req_valid && !imem_if.req_ready) i_request_wait<=i_request_wait+1;
            if(dmem_if.req_valid && !dmem_if.req_ready) d_request_wait<=d_request_wait+1;
            if(i_busy && !imem_if.resp_valid) i_response_wait<=i_response_wait+1;
            if(d_busy && !dmem_if.resp_valid) d_response_wait<=d_response_wait+1;
            if(imem_if.resp_valid && !imem_if.resp_ready) i_response_backpressure<=i_response_backpressure+1;
            if(dmem_if.resp_valid && !dmem_if.resp_ready) d_response_backpressure<=d_response_backpressure+1;
            if(imem_if.resp_valid && imem_if.resp_ready) begin
                imem_if.resp_valid<=0; i_busy<=0; i_completed<=i_completed+1;
                if(imem_if.resp_error) i_errors<=i_errors+1;
                i_rng<=next_random(i_rng); i_stall<=next_random(i_rng)%(stall_max+1);
            end
            if(dmem_if.resp_valid && dmem_if.resp_ready) begin
                dmem_if.resp_valid<=0; d_busy<=0; d_completed<=d_completed+1;
                if(dmem_if.resp_error) d_errors<=d_errors+1;
                d_rng<=next_random(d_rng); d_stall<=next_random(d_rng)%(stall_max+1);
            end
            if(i_accept) begin
                i_busy<=1; i_accepted<=i_accepted+1; i_gap<=i_interval-1;
                i_addr_q<=imem_if.req_addr; i_id_q<=imem_if.req_id; i_left<=i_latency-1; i_error_q<=i_bad;
                if(i_error_enabled && imem_if.req_addr==i_error_addr) i_injected<=1;
            end else if(i_busy && !imem_if.resp_valid && i_left>1) i_left<=i_left-1;
            if(d_accept) begin
                d_busy<=1; d_accepted<=d_accepted+1; d_gap<=d_interval-1;
                d_addr_q<=dmem_if.req_addr; d_id_q<=dmem_if.req_id; d_left<=d_latency-1;
                d_size_q<=dmem_if.req_size; d_write_q<=dmem_if.req_write;
                d_data_q<=dmem_if.req_wdata; d_mask_q<=dmem_if.req_wstrb; d_error_q<=d_bad;
                if(d_error_enabled && dmem_if.req_addr==d_error_addr &&
                   (d_error_write<0 || d_error_write==int'(dmem_if.req_write))) d_injected<=1;
            end else if(d_busy && !dmem_if.resp_valid && d_left>1) d_left<=d_left-1;
            if(i_serve) begin
                imem_if.resp_valid<=1; imem_if.resp_id<=i_accept ? imem_if.req_id : i_id_q;
                imem_if.resp_error<=i_accept ? i_bad : i_error_q;
                imem_if.resp_rdata<=(i_accept ? i_bad : i_error_q) ? 0 : read_lanes(i_accept ? imem_if.req_addr : i_addr_q,2);
            end
            if(d_serve) begin : finish_data
                logic bad,wr;
                logic[31:0] addr,data;
                logic[3:0] mask;
                bad=d_accept ? d_bad : d_error_q; wr=d_accept ? dmem_if.req_write : d_write_q;
                addr=d_accept ? dmem_if.req_addr : d_addr_q; data=d_accept ? dmem_if.req_wdata : d_data_q;
                mask=d_accept ? dmem_if.req_wstrb : d_mask_q;
                dmem_if.resp_valid<=1; dmem_if.resp_id<=d_accept ? dmem_if.req_id : d_id_q;
                dmem_if.resp_error<=bad;
                dmem_if.resp_rdata<=bad || wr ? 0 : read_lanes(addr,d_accept ? dmem_if.req_size : d_size_q);
                if(!bad && wr) begin
                    for(int b=0;b<4;b++) if(mask[b]) mem[(addr-BASE)>>2][8*b+:8]<=data[8*b+:8];
                    store_writes<=store_writes+1;
                end
            end
        end
    end
    a_i_response_hold: assert property (@(posedge clk) disable iff(!rst_n)
        imem_if.resp_valid && !imem_if.resp_ready |=> imem_if.resp_valid &&
        $stable({imem_if.resp_id,imem_if.resp_rdata,imem_if.resp_error}));
    a_d_response_hold: assert property (@(posedge clk) disable iff(!rst_n)
        dmem_if.resp_valid && !dmem_if.resp_ready |=> dmem_if.resp_valid &&
        $stable({dmem_if.resp_id,dmem_if.resp_rdata,dmem_if.resp_error}));
    // Inspection helper, never an extra CPU memory port.
    function automatic logic[31:0] peek_word(input logic[31:0] address);
        if(address<BASE || (address-BASE)>=32'(WORDS*4)) return 0;
        return mem[(address-BASE)>>2];
    endfunction
endmodule
