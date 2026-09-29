; Boot ROM for tools/timing.py: a 256 KB Kickstart image for vAmiga.
;
; tools/timing.py assembles it with these defines:
;   EXCERPT_AT  where the excerpt runs, in chip RAM
;   ENTRY       the excerpt's entry point
;   START_LINE  the raster line that starts the call
;   BITPLANES   low-resolution bitplanes to fetch during the call; 0: none
; and these files in the include path:
;   excerpt.bin the replay code, assembled at EXCERPT_AT
;   writes.bin  a word count, then per write: a long address, a word size
;               (1, 2 or 4) and a long value

        org     $fc0000
        dc.w    $1111
        dc.w    $4ef9           ; jmp: reset reads its address as the PC
        dc.l    start

COPPER_AT       equ     $1000   ; the copper reads chip RAM only

start:
        lea     $80000,sp       ; the top of chip RAM; reset's is odd
        move.b  #3,$bfe201      ; CIA-A: LED and overlay are outputs
        move.b  #2,$bfe001      ; overlay off: chip RAM at 0
        move.w  #$7fff,$dff096  ; all DMA off
        move.w  #$7fff,$dff09a  ; all interrupts off

; vAmiga sets up bitplane DMA at the first frame's last line.
frame:
        move.l  $dff004,d0
        and.l   #$1ff00,d0
        cmp.l   #312<<8,d0
        bne.s   frame

        lea     excerpt(pc),a0
        lea     EXCERPT_AT,a1
        move.w  #(excerpt_end-excerpt)/2-1,d0
copy:
        move.w  (a0)+,(a1)+
        dbra    d0,copy

        lea     writes(pc),a0
        move.w  (a0)+,d1
        bra.s   .next
.write:
        move.l  (a0)+,a1
        move.w  (a0)+,d0
        move.l  (a0)+,d2
        cmp.w   #1,d0
        beq.s   .byte
        cmp.w   #2,d0
        beq.s   .word
        move.l  d2,(a1)
        bra.s   .next
.byte:
        move.b  d2,(a1)
        bra.s   .next
.word:
        move.w  d2,(a1)
.next:
        dbra    d1,.write

        ifne    BITPLANES
        move.w  #BITPLANES<<12|$200,$dff100     ; BPLCON0: colour on
        move.w  #$0038,$dff092  ; DDFSTRT
        move.w  #$00d0,$dff094  ; DDFSTOP
        move.w  #$2c81,$dff08e  ; DIWSTRT
        move.w  #$2cc1,$dff090  ; DIWSTOP
        lea     $dff0e0,a0      ; BPL1PT
        moveq   #BITPLANES-1,d0
planes:
        move.l  #$70000,(a0)+
        dbra    d0,planes
        move.w  #$8300,$dff096  ; DMACON: DMA and bitplanes on
        endc

; Start the call from the copper interrupt at START_LINE: stop wakes at a
; fixed beam position, whatever the code before it takes.
        move.l  #call,$6c       ; level 3 vector
        lea     copper(pc),a0
        lea     COPPER_AT,a1
        move.l  (a0)+,(a1)+
        move.l  (a0)+,(a1)+
        move.l  (a0)+,(a1)+
        move.l  #COPPER_AT,$dff080      ; COP1LC
        move.w  d0,$dff088      ; COPJMP1
        move.w  #$8280,$dff096  ; DMACON: DMA and copper on
        move.w  #$c010,$dff09a  ; INTENA: copper interrupt on
        stop    #$2000
call:
        move.w  #$0010,$dff09c  ; INTREQ: copper interrupt done
        jsr     ENTRY
done:
        bra.s   done

        cnop    0,4
copper:
        dc.w    START_LINE<<8|$01,$fffe ; wait for the line
        dc.w    $009c,$8010     ; INTREQ: copper interrupt
        dc.w    $ffff,$fffe     ; wait forever

excerpt:
        incbin  "excerpt.bin"
excerpt_end:
        even
writes:
        incbin  "writes.bin"

        cnop    0,$40000
