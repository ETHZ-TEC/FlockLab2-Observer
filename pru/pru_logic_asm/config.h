/**
 * Copyright (c) 2020, ETH Zurich, Computer Engineering Group
 * All rights reserved.
 *
 * Redistribution and use in source and binary forms, with or without
 * modification, are permitted provided that the following conditions are met:
 *
 * * Redistributions of source code must retain the above copyright notice, this
 *   list of conditions and the following disclaimer.
 *
 * * Redistributions in binary form must reproduce the above copyright notice,
 *   this list of conditions and the following disclaimer in the documentation
 *   and/or other materials provided with the distribution.
 *
 * * Neither the name of the copyright holder nor the names of its
 *   contributors may be used to endorse or promote products derived from
 *   this software without specific prior written permission.
 *
 * THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
 * AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
 * IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
 * ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
 * LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
 * CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
 * SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
 * INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
 * CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
 * ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
 * POSSIBILITY OF SUCH DAMAGE.
 * 
 * Author: Reto Da Forno
 */

/*
 * Beaglebone PRU1 firmware config for FlockLab2 GPIO tracing
 */

#ifndef __PRU_LOGIC_CONFIG_H__
#define __PRU_LOGIC_CONFIG_H__

/* parameters */
#define USE_SCRATCHPAD      1           /* utilize PRU0 to transfer the samples */
#define USE_CYCLE_COUNTER   0           /* use hardware cycle counter for timestamping instead of counting loop passes (max. sampling rate will be reduced) */
#if USE_CYCLE_COUNTER
 #define SAMPLING_RATE      6250000     /* in Hz (do not change) */
#else /* USE_CYCLE_COUNTER */
 #define SAMPLING_RATE      10000000    /* in Hz (1 - 10000000) */
#endif /* USE_CYCLE_COUNTER */

/* fixed values */
#define PRU_FREQ            200000000   /* in Hz (don't change!) */

/* parameter checks */
#if SAMPLING_FREQ > 10000000
 #error "max sampling frequency is 10MHz"
#endif

#if USE_SCRATCHPAD && USE_CYCLE_COUNTER
 #error "cannot use scratchpad and cycle counter at the same time"
#endif

#if USE_CYCLE_COUNTER && (SAMPLING_RATE != (PRU_FREQ >> 5))
 #error "invalid sampling rate"
#endif

#endif /* __PRU_LOGIC_CONFIG_H__ */
