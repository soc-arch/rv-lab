// =============================================================================
// HY-RV | mem_if
// Description: Independent ready/valid memory request and completion channels.
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

// HY-RV memory v1: independent ready/valid request and completion channels.
// Payload remains stable under backpressure. Every accepted read OR write has
// exactly one response; minimum response latency is one cycle. See rtl/README.md.
interface mem_if #(parameter int ADDR_W=32, DATA_W=32, ID_W=1);
    localparam int SIZE_W = ($clog2($clog2(DATA_W/8)+1) < 1) ? 1 : $clog2($clog2(DATA_W/8)+1);
    initial begin
        assert (ADDR_W>0 && ID_W>0);
        assert (DATA_W>=32 && ((DATA_W & (DATA_W-1))==0));
    end
    logic req_valid, req_ready;
    logic [ID_W-1:0] req_id;
    logic [ADDR_W-1:0] req_addr;
    logic req_write;
    logic [SIZE_W-1:0] req_size;
    logic [DATA_W-1:0] req_wdata;
    logic [DATA_W/8-1:0] req_wstrb;
    logic [1:0] req_memtype, req_priv;
    logic resp_valid, resp_ready;
    logic [ID_W-1:0] resp_id;
    logic [DATA_W-1:0] resp_rdata;
    logic resp_error;
    modport master(output req_valid,req_id,req_addr,req_write,req_size,req_wdata,
        req_wstrb,req_memtype,req_priv,resp_ready,
        input req_ready,resp_valid,resp_id,resp_rdata,resp_error);
    modport slave(input req_valid,req_id,req_addr,req_write,req_size,req_wdata,
        req_wstrb,req_memtype,req_priv,resp_ready,
        output req_ready,resp_valid,resp_id,resp_rdata,resp_error);
endinterface
