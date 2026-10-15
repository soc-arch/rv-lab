// Local editable teaching snapshot; see SOURCE_SNAPSHOT.json for provenance.
// =============================================================================
// rv32_alu_op_decode — RV32I ALU op encoding from (opcode/funct3/funct7)
//

//
// fu_alu op encoding (from fu_alu.sv / datapath_p0_p1.md §1.3):
//   ADD=0, SUB=1, AND=2, OR=3, XOR=4, SLL=5, SRL=6, SRA=7,
//   SLT=8, SLTU=9, PASS_B=10 (for LUI)
//



//

// =============================================================================

module rv32_alu_op_decode (
    input  logic [2:0] funct3,
    input  logic       funct7_bit5,   // funct7[5] (SUB/SRA distinguishing bit)
    input  logic       is_alu_imm,
    input  logic       is_alu_reg,    // true → OP (R-type): full sub/shift set
    output logic [3:0] alu_op
);

    localparam logic [3:0] ALU_ADD    = 4'd0;
    localparam logic [3:0] ALU_SUB    = 4'd1;
    localparam logic [3:0] ALU_AND    = 4'd2;
    localparam logic [3:0] ALU_OR     = 4'd3;
    localparam logic [3:0] ALU_XOR    = 4'd4;
    localparam logic [3:0] ALU_SLL    = 4'd5;
    localparam logic [3:0] ALU_SRL    = 4'd6;
    localparam logic [3:0] ALU_SRA    = 4'd7;
    localparam logic [3:0] ALU_SLT    = 4'd8;
    localparam logic [3:0] ALU_SLTU   = 4'd9;

    always_comb begin
        alu_op = ALU_ADD;   // safe default

        if (is_alu_imm) begin
            // ADDI, SLTI, SLTIU, XORI, ORI, ANDI, SLLI, SRLI/SRAI.

            case (funct3)
                3'b000:  alu_op = ALU_ADD;
                3'b010:  alu_op = ALU_SLT;
                3'b011:  alu_op = ALU_SLTU;
                3'b100:  alu_op = ALU_XOR;
                3'b110:  alu_op = ALU_OR;
                3'b111:  alu_op = ALU_AND;
                3'b001:  alu_op = ALU_SLL;
                3'b101:  alu_op = funct7_bit5 ? ALU_SRA : ALU_SRL;
                default: alu_op = ALU_ADD;
            endcase
        end else if (is_alu_reg) begin
            // ADD/SUB, SLL, SLT, SLTU, XOR, SRL/SRA, OR, AND.
            case (funct3)
                3'b000:  alu_op = funct7_bit5 ? ALU_SUB : ALU_ADD;
                3'b001:  alu_op = ALU_SLL;
                3'b010:  alu_op = ALU_SLT;
                3'b011:  alu_op = ALU_SLTU;
                3'b100:  alu_op = ALU_XOR;
                3'b101:  alu_op = funct7_bit5 ? ALU_SRA : ALU_SRL;
                3'b110:  alu_op = ALU_OR;
                3'b111:  alu_op = ALU_AND;
                default: alu_op = ALU_ADD;
            endcase
        end
        // else: not ALU; caller is responsible (LUI → PASS_B, AUIPC → ADD, etc).
    end

endmodule
