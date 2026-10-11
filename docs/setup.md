# Setup: choose a machine and check the tools

Use this guide before [Lab 01](course/01-setup.md). The labs run on Linux and use
an independent teaching CPU. You need a terminal, basic C knowledge, and a modern
browser. No FPGA or physical camera is needed.

## 1. Choose where the commands will run

| Your computer | Recommended workspace |
| --- | --- |
| Staff-equipped laboratory server | Log in to your student account; select the tool environment supplied by your instructor |
| Linux computer | Install the open-source tools below, then work in your own home directory |
| Windows computer | Use a Linux distribution under WSL, or connect to the laboratory server |
| Mac | Use Terminal to connect to the Linux laboratory server |

For WSL, follow [Microsoft's official installation guide](https://learn.microsoft.com/en-us/windows/wsl/install)
and run the lab commands inside the Linux terminal. Keep the clone in the Linux
home directory. WSL and native macOS execution are not part of the server's
validation record; run Lab 01 to check your selected environment.

On a laboratory server, the instructor provides the login address, account and
tool-selection instructions. Load that environment in every new terminal before
running `make doctor`. Tool installation is a staff prerequisite there; students
do not need administrator access to run these labs.

On the laboratory's Voyager server, the shared tools are selected with:

```sh
source /tools/rv-lab/env.sh
```

Run this in each new Bash terminal. It selects the shared RISC-V compiler, Spike,
Verilator, host compiler, and Python. On another machine, use the environment
provided by its instructor or your own installed tools instead.

## 2. Clone your own workspace

In the Linux terminal:

```sh
git clone https://github.com/soc-arch/rv-lab.git ~/rv-lab
cd ~/rv-lab
mkdir -p student
```

Keep your applications in `student/`. Generated files go to `build/`; each lesson
selects `LAB_BUILD_DIR="$PWD/build/course"` so its results stay together. Keep
`rtl/` unchanged during the eight introductory software exercises. If `~/rv-lab`
already exists, choose another new clone directory and use that path consistently.

## 3. Check prerequisites and versions

```sh
cd ~/rv-lab
make doctor
```

Record the executable paths and versions printed by the doctor. Availability
alone does not establish a passing simulation; the comparison and smoke gate in
Lab 01 supply that evidence.

| Tool | Requirement | Official installation/reference |
| --- | --- | --- |
| Python | Python 3.8 or later; the core runner and manual use the standard library | [Python downloads](https://www.python.org/downloads/) |
| Make and host C++ compiler | GNU Make and a C++ compiler supported by the chosen Verilator | [GNU Make](https://www.gnu.org/software/make/), [Verilator prerequisites](https://verilator.org/guide/latest/install.html) |
| RISC-V GCC/binutils | Bare-metal compiler supporting `-march=rv32im -mabi=ilp32` | [RISC-V GNU toolchain](https://github.com/riscv-collab/riscv-gnu-toolchain) |
| Spike | RISC-V ISA simulator executable | [Spike build steps](https://github.com/riscv-software-src/riscv-isa-sim#build-steps) |
| Verilator | A compatible Verilator installation, checked by the first hardware run | [Verilator installation](https://verilator.org/guide/latest/install.html) |
| Pillow, optional | Only for PNG/JPEG inputs or image resizing | [Pillow installation](https://pillow.readthedocs.io/en/stable/installation/basic-installation.html) |

A compiler named `riscv64-unknown-elf-gcc` can generate this 32-bit target if it
supports the required architecture and ABI. A Linux-target compiler named
`riscv64-unknown-linux-gnu-gcc` is a different toolchain. This lab supplies its
own startup and small runtime rather than linking a full C library. It does
not need the Spike proxy kernel (`pk`).

The runner searches `PATH` and `$HOME/tools/riscv/bin`. If your tools are installed
elsewhere, replace the following example paths with real installed paths:

```sh
export CROSS_COMPILE=/your/toolchain/bin/riscv32-unknown-elf-
export SPIKE=/your/spike/bin/spike
export VERILATOR=/your/verilator/bin/verilator
export CXX=/your/compiler/bin/g++
make doctor
```

For the 64-bit-named bare-metal compiler, set `CROSS_COMPILE` to its
`riscv64-unknown-elf-` prefix instead. Choose and record tool revisions when
installing locally; a different installation must pass its own baseline checks.
Follow the official upstream instructions for your Linux distribution rather
than treating this repository as a tool installer.

## 4. Establish a passing baseline

```sh
cd ~/rv-lab
export LAB_BUILD_DIR="$PWD/build/course"
make compare APP=01_arithmetic
make test-smoke
```

The first hardware run builds the RTL simulator and may take longer. Expect the
arithmetic program to pass its checks and print `COMPARE PASS` for matching
complete signatures. The smoke suite has 17 cases: three deliberately test
failure detection. Read the final suite summary; those three intended failures
do not mean the installation is broken.

If the baseline fails unexpectedly, keep the command, output directory and logs.
Resolve correctness before continuing to performance comparisons.

## 5. Open your generated manual and results

Generate the local manual in your main terminal:

```sh
make course
```

In a second Linux terminal, select the same workspace and build directory:

```sh
cd ~/rv-lab
LAB_BUILD_DIR="$PWD/build/course" make serve PORT=8771
```

Leave it running. On the same computer, open these browser addresses:

- Manual: `http://127.0.0.1:8771/course/index.html`
- Application results: `http://127.0.0.1:8771/results.html`
- Gallery: `http://127.0.0.1:8771/`

The public [HTML course website](https://soc-arch.github.io/rv-lab/) contains the
instructions. It does not run simulations or store your program results. The
addresses above refer to your own generated results, available after the matching
commands finish. Refresh the browser after rerunning an experiment. Use a browser
to render HTML; an editor's source tab shows the page's code.

## 6. Open remote results through SSH

When simulation runs on the Linux server, `127.0.0.1` in your laptop's browser
refers to the laptop. Keep the result server from Step 5 running on Linux. In a
separate terminal **on your laptop**, run:

```sh
ssh -N -o ExitOnForwardFailure=yes -L 8771:127.0.0.1:8771 your-user@your-lab-server
```

Replace the user and server with the details supplied by your instructor. After
successful login, this command stays quiet and does not show a shell prompt:
`-N` keeps only the forwarding connection open. Leave that terminal running and
open `http://127.0.0.1:8771/course/index.html` or the results URL on your laptop.
Stop the tunnel and result server with Ctrl-C when finished.

If laptop port 8771 is occupied, choose a different laptop port:

```sh
ssh -N -o ExitOnForwardFailure=yes -L 8772:127.0.0.1:8771 your-user@your-lab-server
```

Then open `http://127.0.0.1:8772/` on the laptop. The final `8771` remains the
port used by the server's `make serve` command. If you change the server port,
change that final number as well.

## 7. Troubleshooting

| Observation | Check and next step |
| --- | --- |
| `make` or `python3` is missing | On a lab server, load the staff environment; on your Linux computer, install the prerequisites and rerun the doctor |
| Compiler, Spike or Verilator is missing | Inspect `PATH` and the four tool selections above; use the official installation instructions or ask staff for the installed paths |
| First hardware command is taking time | Wait for the simulator build; preserve a reported compiler error or timeout rather than assuming it passed |
| Smoke prints some failed application checks | Three failures are intentional; require the overall 17-case expected-outcome summary to pass |
| SSH reports `Permission denied` | Confirm the server and account and correct your login method; a failed login does not establish a tunnel |
| SSH is quiet after login | This is normal for `ssh -N`; keep it running and open the matching browser port |
| `Address already in use` | Choose another port; match the browser's laptop port and the tunnel's destination server port |
| Browser cannot connect | Confirm `make serve` is still running, the selected build directory is correct, and the tunnel/browser ports agree |
| Result page does not exist yet | Run the corresponding experiment successfully; the public course website does not contain your results |
| No live `printf` output or a timeout | The 1024-byte console is shown after completion; shorten the input or inspect a bounded trace |
| Custom-source build fails | Use a real file under `student/`, preserve the first error and confirm the freestanding runtime's supported operations |

Continue with [Lab 01: Setup and baseline](course/01-setup.md), then follow the
eight labs in order.
