Play:
 bsr	next	; appelé
 rts
next:
 move.w	#next-Play,d0
 rts
