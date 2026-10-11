OUTPUT_ARCH(riscv)
ENTRY(_start)
MEMORY { RAM (rwx) : ORIGIN = 0x80000000, LENGTH = 1M }
SECTIONS {
  .text : { KEEP(*(.text.init)) *(.text .text.*) } > RAM
  .rodata : { *(.rodata .rodata.* .srodata .srodata.*) } > RAM
  .data : { *(.data .data.*) . = ALIGN(4); __global_pointer$ = . + 0x800; *(.sdata .sdata.*) } > RAM
  .htif ALIGN(64) : { KEEP(*(.htif)) } > RAM
  .signature ALIGN(16) : {
    begin_signature = .; KEEP(*(.signature));
    /* Optional application output, e.g. an image, in the same host dump. */
    KEEP(*(.signature_extra .signature_extra.*));
    . = ALIGN(16); end_signature = .;
  } > RAM
  .bss (NOLOAD) : {
    . = ALIGN(4); __bss_start = .;
    *(.sbss .sbss.* .bss .bss.*) *(COMMON)
    . = ALIGN(4); __bss_end = .;
  } > RAM
  __stack_top = ORIGIN(RAM) + LENGTH(RAM);
  ASSERT(__bss_end + 16384 <= __stack_top, "Keep at least 16 KiB for the stack")
}
