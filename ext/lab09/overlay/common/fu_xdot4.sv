// =============================================================================
// HY-RV | fu_xdot4
// Description: Lab 09 XDOT4 building block: four signed int8 products and their sum.
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

// Combinational unit beside fu_alu. It completes in the same cycle as an ALU
// instruction, so the backend needs no new state for it.
//
//   result = sext32( a.byte[0]*b.byte[0] + a.byte[1]*b.byte[1]
//                  + a.byte[2]*b.byte[2] + a.byte[3]*b.byte[3] )
//
// Byte 0 is bits 7:0. Every byte is a signed int8 (-128..127).
// Range of the sum: -65,024 .. +65,536, so 18 signed bits are enough.
module fu_xdot4 (
    input  logic [31:0] a,       // rs1 value: four packed int8
    input  logic [31:0] b,       // rs2 value: four packed int8
    output logic [31:0] result   // value written to rd
);
    // TODO(lab09-2): compute the four signed int8 products and their sum.
    //   Hints: a[8*i +: 8] selects byte i. $signed(...) makes a value signed.
    //   A signed 8x8 product needs 16 bits; the sum of four needs 18 bits.
    //   Sign-extend the 18-bit sum to the 32-bit result.
    //   Check: a=0x04030201, b=0x08070605 -> 70 (0x00000046).
    //          a=0xFC03FE01, b=0x02FF0403 -> -16 (0xFFFFFFF0).
    assign result = 32'd0;
endmodule
