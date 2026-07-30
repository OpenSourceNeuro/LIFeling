.ALIASES
R_R1            R1(1=N01525 2=VPU ) CN @TLV7041_PSPICE.SCHEMATIC1(sch_1):INS598@ANALOG.R.Normal(chips)
V_V4            V4(+=VPU -=0 ) CN @TLV7041_PSPICE.SCHEMATIC1(sch_1):INS692@SOURCE.VDC.Normal(chips)
V_V1            V1(+=IN+ -=0 ) CN @TLV7041_PSPICE.SCHEMATIC1(sch_1):INS708@SOURCE.VSIN.Normal(chips)
V_V2            V2(+=IN- -=0 ) CN @TLV7041_PSPICE.SCHEMATIC1(sch_1):INS660@SOURCE.VDC.Normal(chips)
V_V3            V3(+=V+ -=0 ) CN @TLV7041_PSPICE.SCHEMATIC1(sch_1):INS676@SOURCE.VDC.Normal(chips)
X_U1            U1(IN+=IN+ IN-=IN- OUT=N01525 V+=V+ V-=0 ) CN
+@TLV7041_PSPICE.SCHEMATIC1(sch_1):INS1155@TESTING.TLV7041_0.Normal(chips)
_    _(V-=0)
_    _(IN+=IN+)
_    _(IN-=IN-)
_    _(V+=V+)
_    _(Vpu=VPU)
.ENDALIASES
