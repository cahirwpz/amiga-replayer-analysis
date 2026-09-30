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

; Names follow the NDK's hardware/*.i.
custom  equ     $dff000
vposr   equ     $004
cop1lc  equ     $080
copjmp1 equ     $088
diwstrt equ     $08e
diwstop equ     $090
ddfstrt equ     $092
ddfstop equ     $094
dmacon  equ     $096
intena  equ     $09a
intreq  equ     $09c
bplpt   equ     $0e0
bplcon0 equ     $100

DMAF_SETCLR equ $8000
DMAF_COPPER equ $0080
DMAF_RASTER equ $0100
DMAF_MASTER equ $0200

INTF_SETCLR equ 1<<15
INTF_INTEN equ  1<<14
INTF_COPER equ  1<<4

BPLCON0_COLOR equ $0200
CLEAR_ALL equ   $7fff           ; every bit but SETCLR

ciaa    equ     $bfe001
ciapra  equ     $0000
ciaddra equ     $0200
CIAF_LED equ    1<<1
CIAF_OVERLAY equ 1<<0

CHIP_END equ    $80000          ; the top of 512 KB chip RAM
LEVEL3_VECTOR equ $6c
COPPER_AT equ   $1000           ; the copper reads chip RAM only
PLANES_AT equ   $70000

        ifne    BITPLANES
RASTER_DMA equ  DMAF_RASTER
        else
RASTER_DMA equ  0
        endc

        org     $fc0000
        dc.w    $1111
        dc.w    $4ef9           ; jmp: reset reads its address as the PC
        dc.l    start

start:
        lea     CHIP_END,sp     ; reset's is odd
        lea     custom,a6
        move.b  #CIAF_LED|CIAF_OVERLAY,ciaa+ciaddra ; outputs
        move.b  #CIAF_LED,ciaa+ciapra ; overlay off: chip RAM at 0
        move.w  #CLEAR_ALL,dmacon(a6)
        move.w  #CLEAR_ALL,intena(a6)

; vAmiga sets up bitplane DMA at the first frame's last line.
frame:
        move.l  vposr(a6),d0
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
        move.w  #BITPLANES<<12|BPLCON0_COLOR,bplcon0(a6)
        move.w  #$0038,ddfstrt(a6)
        move.w  #$00d0,ddfstop(a6)
        move.w  #$2c81,diwstrt(a6)
        move.w  #$2cc1,diwstop(a6)
        endc

; Start the call from the copper interrupt at START_LINE: stop wakes at a
; fixed beam position, whatever the code before it takes.
        move.l  #call,LEVEL3_VECTOR
        lea     copper(pc),a0
        lea     COPPER_AT,a1
        move.w  #(copper_end-copper)/4-1,d0
.copper:
        move.l  (a0)+,(a1)+
        dbra    d0,.copper
        move.l  #COPPER_AT,cop1lc(a6)
        move.w  d0,copjmp1(a6)
        move.w  #DMAF_SETCLR|DMAF_MASTER|DMAF_COPPER|RASTER_DMA,dmacon(a6)
        move.w  #INTF_SETCLR|INTF_INTEN|INTF_COPER,intena(a6)
        stop    #$2000
call:
; An absolute address: data/timing/*.yaml were measured with its bus reads.
        move.w  #INTF_COPER,custom+intreq ; done
        jsr     ENTRY
done:
        bra.s   done

        cnop    0,4
; The copper restarts at each frame; it points the bitplanes at PLANES_AT.
copper:
PLANE   set     0
        rept    BITPLANES
        dc.w    bplpt+PLANE*4,PLANES_AT>>16
        dc.w    bplpt+PLANE*4+2,PLANES_AT&$ffff
PLANE   set     PLANE+1
        endr
        dc.w    START_LINE<<8|$01,$fffe ; wait for the line
        dc.w    intreq,INTF_SETCLR|INTF_COPER
        dc.w    $ffff,$fffe     ; wait forever
copper_end:

excerpt:
        incbin  "excerpt.bin"
excerpt_end:
        even
writes:
        incbin  "writes.bin"

        cnop    0,$40000
