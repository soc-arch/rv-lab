PYTHON ?= python3
APP ?= 01_arithmetic
OPT ?= O2
ITERATIONS ?= 1
CAMERA_MODE ?= pipeline
PORT ?= 8770
MEMORY ?= fast
TRACE_LIMIT ?= 20000
FRAME ?= 0
NOISE_SEED ?= 1
ifneq ($(RTL_DIR),)
export LAB_RTL_DIR := $(RTL_DIR)
endif
ARGS = --app $(APP) --opt $(OPT) --iterations $(ITERATIONS)
ARGS += --camera-mode $(CAMERA_MODE)
ARGS += --memory-profile $(MEMORY) --trace-limit $(TRACE_LIMIT)
ARGS += --frame $(FRAME) --noise-seed $(NOISE_SEED)
ifneq ($(NAME),)
ARGS += --name "$(NAME)"
endif
ifneq ($(TITLE),)
ARGS += --title "$(TITLE)"
endif
ifneq ($(DESCRIPTION),)
ARGS += --description "$(DESCRIPTION)"
endif
ifeq ($(CSR),1)
ARGS += --csr-counters
endif
ifeq ($(COMMITS),1)
ARGS += --commit-log
endif
ifneq ($(CLOCK_MHZ),)
ARGS += --clock-mhz $(CLOCK_MHZ)
endif
ifneq ($(I_LATENCY),)
ARGS += --i-latency $(I_LATENCY)
endif
ifneq ($(D_LATENCY),)
ARGS += --d-latency $(D_LATENCY)
endif
ifneq ($(I_INTERVAL),)
ARGS += --i-interval $(I_INTERVAL)
endif
ifneq ($(D_INTERVAL),)
ARGS += --d-interval $(D_INTERVAL)
endif
ifneq ($(STALL_SEED),)
ARGS += --stall-seed $(STALL_SEED)
endif
ifneq ($(STALL_MAX),)
ARGS += --stall-max $(STALL_MAX)
endif
ifneq ($(INPUT),)
ARGS += --input "$(INPUT)"
endif
ifneq ($(WIDTH),)
ARGS += --width $(WIDTH)
endif
ifneq ($(HEIGHT),)
ARGS += --height $(HEIGHT)
endif
ifneq ($(TRACE_SYMBOL),)
ARGS += --trace-symbol $(TRACE_SYMBOL)
endif
ifneq ($(SOURCE),)
ARGS += --source "$(SOURCE)"
endif
ifneq ($(RTL_DIR),)
ARGS += --rtl-dir "$(RTL_DIR)"
endif
ifeq ($(TRACE),1)
ARGS += --trace
endif
ifeq ($(WAVE),1)
ARGS += --wave
endif
ifeq ($(VALIDATION),1)
ARGS += --validation
endif
.PHONY: help doctor build sw-sim hw-sim compare view register course site site-check course-test test test-smoke memory-test coremark export export-views camera visual images gallery serve camera-test visual-test validate viewer-test perf-test registration-test
help:
	@echo 'make doctor | sw-sim | hw-sim | compare | view | test | coremark | camera | visual | images | gallery | serve | export'
	@echo 'APP=01_arithmetic..05_functions, 06_camera, 07_denoise, 08_cartoon, 09_ball, 10_performance or coremark'
	@echo 'CAMERA_MODE=copy|grayscale|sobel|pipeline INPUT=frame.ppm WIDTH=80 HEIGHT=60'
	@echo 'TRACE=1 WAVE=1 RTL_DIR=/path/to/your/rtl ITERATIONS=1 VALIDATION=1'
	@echo 'MEMORY=fast|latency2|latency3|stress; I_LATENCY/D_LATENCY, I_INTERVAL/D_INTERVAL, STALL_SEED/STALL_MAX'
	@echo 'test-smoke: original 17 cases; test: full application + memory protocol regression'
	@echo 'validate: reproducibility gates with source receipts; LAB_BUILD_DIR isolates candidate outputs'
	@echo 'CSR=1: optional software cycle/instret counters; COMMITS=1: full retired-instruction log; CLOCK_MHZ=100: assumed frequency'
	@echo 'course: step-by-step English exercises; register SOURCE=my_main.c NAME=my-sum TITLE="My sum": verify and add to My applications'
doctor:
	$(PYTHON) lab.py doctor
build:
	$(PYTHON) lab.py build $(ARGS)
sw-sim:
	$(PYTHON) lab.py run --backend sw $(ARGS)
hw-sim:
	$(PYTHON) lab.py run --backend hw $(ARGS)
compare:
	$(PYTHON) lab.py run --backend both $(ARGS)
view:
	$(PYTHON) lab.py run --backend hw --trace $(ARGS)
register:
	$(PYTHON) lab.py register $(ARGS)
course:
	$(PYTHON) lab.py course
site:
	$(PYTHON) tools/build_site.py
site-check:
	$(PYTHON) tools/check_site.py
course-test:
	$(PYTHON) -m unittest discover -s tests -p 'test_course.py' -v
test:
	$(PYTHON) lab.py test $(ARGS)
test-smoke:
	$(PYTHON) lab.py test --suite smoke $(ARGS)
memory-test:
	$(PYTHON) tests/memory_protocol.py $(if $(RTL_DIR),--rtl-dir "$(RTL_DIR)")
coremark:
	$(PYTHON) lab.py run --backend both $(ARGS) --app coremark
export:
	$(PYTHON) lab.py export
export-views:
	$(PYTHON) lab.py export-views
camera:
	$(PYTHON) lab.py camera --trace $(ARGS)
visual:
	$(PYTHON) lab.py visual --trace $(ARGS)
images: camera visual
gallery:
	$(PYTHON) lab.py gallery $(ARGS)
serve:
	$(PYTHON) lab.py serve --port $(PORT)
camera-test:
	$(PYTHON) -m unittest discover -s tests -p test_camera_lab.py -v
visual-test:
	$(PYTHON) -m unittest discover -s tests -p test_visual_lab.py -v
viewer-test:
	$(PYTHON) -m unittest discover -s tests -p test_viewer_catalog.py -v
validate:
	$(PYTHON) verify.py $(if $(RTL_DIR),--rtl-dir "$(RTL_DIR)")
perf-test:
	$(PYTHON) -m unittest discover -s tests -p 'test_performance*.py' -v
	$(PYTHON) -m unittest discover -s tests -p 'test_student_workflow.py' -v
registration-test:
	$(PYTHON) -m unittest discover -s tests -p 'test_registration.py' -v
