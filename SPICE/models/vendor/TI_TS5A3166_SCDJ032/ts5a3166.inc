******************************************************************************
* *
* TEXAS INSTRUMENTS INCORPORATED
* Standard Linear and Logic Group
* HSPICE Model for TS5A3166
* PROPERTY OF TEXAS INSTRUMENTS INCORPORATED. UNAUTHORIZED
* REPRODUCTION AND/OR DISTRIBUTION IS STRICTLY PROHIBITED.
*
* THIS PRODUCT IS PROTECTED UNDER COPYRIGHT LAW.
* CREATED 2005, (C) COPYRIGHT 2005, TEXAS INSTRUMENTS
* INCORPORATED, ALL RIGHTS RESERVED
*
* UNLESS THERE IS A SIGNED, WRITTEN AGREEMENT TO THE
* CONTRARY, TEXAS INSTRUMENTS (TI) IS PROVIDING THE IBIS
* MODELS AND WITHOUT ANY WARRANTY, EXPRESSED OR
* IMPLIED. TI ASSUMES NO LIABILITY FOR:
* 1) THE ACCURACY OF THE HSPICE MODELS PROVIDED TO YOUR
* COMPANY;
* 2) THE PROPER FUNCTIONING OF THESE HSPICE MODELS IN YOUR
* DESIGN OR FOR ANY RESULTING APPLICATIONS; OR
* 3) INFRINGEMENT OF PATENTS, COPYRIGHTS OR INTELLECTUAL
* PROPERTY RIGHTS RESULTING FROM YOUR USE OF THESE HSPICE
* MODELS.
*
* TI PROVIDES HSPICE MODELS AS A SERVICE TO OUR CUSTOMERS.
* YOU AND YOUR COMPANY SHALL NOT DISTRIBUTE, SELL OR GIVE
* THESE MODELS TO ANYONE ELSE WITHOUT PRIOR WRITTEN
* PERMISSION FROM TI.
*
* TI RESERVES THE RIGHT TO MAKE CHANGES TO OUR PRODUCTS OR
* TO DISCONTINUE ANY SEMICONDUCTOR PRODUCT OR SERVICE
* WITHOUT NOTICE, AND ADVISES OUR CUSTOMERS TO OBTAIN THE
* LATEST VERSION OF RELEVANT INFORMATION TO VERIFY, BEFORE
* PLACING ORDERS, THAT THE INFORMATION BEING RELIED ON IS
* CURRENT.
*
* PLEASE BE AWARE THAT YOUR RECEIPT AND USE OF THE HSPICE
* INFORMATION PROVIDED SHALL SERVE AS ACCEPTANCE OF THESE
* TERMS AND CONDITIONS. IF YOU DO NOT ACCEPT THESE TERMS,
* YOU SHOULD RETURN OR DESTROY THE HSPICE MODELS AND ANY
* OTHER ACCOMPANYING INFORMATION IMMEDIATELY.
* TS5A3166
* HSPICE NETLIST file built on Tue Jan 4 10:41:24 CST 2005
.SUBCKT TS5A3166 PE1 PE2 PE3 PE4 PE5
***PLEASE INCLUDE ONLY ONE PACKAGE***
.INCLUDE 'sot5.pkg'
X_TS5A3166__DIE PI1 PI2 PI3 PI4 PI5 TS5A3166__DIE
***PLEASE INCLUDE ONLY ONE PROCESS***
***NOMINAL or STRONG or WEAK***
.LIB 'ts5a3166_process.lib' NOMINAL
**
** No globals were defined outside of .SUBCKT calls...
**
**
** The following netlist has gone through the hspice netlist cleaner,
** version v2.0 - Nov 20 2003
** on Tue Jan 4 10:41:24 CST 2005
**
* .width IN=256
* .echo on Expansion of
* /share/sll/db/ts5a3166_50b10/da/ts5a3166/SPICE/ts5a3166.spi ()
** Added by cleaner script...
.SUBCKT TS5A3166__DIE A B CGND C CVCC
.prot FREELIB
%K.O$S#/Z=P2P!;ty
kO:$1#/z=p2p!;TY
kOH$-#/z=p2p!;TY
3dgv=#/6k>2[o\;:kGZv7ds+Dd ..\up/x;:0[(Ci10
'=# s: ))7gW+z/hsj# s: )57gd+%XA<SgW%x6ls=5hy
30a:7Gy%kxaA#dw%\>a.=-+(c%:p6ro%6
eU[8[W%9>!8Y#)<%%fL
)z/;-12G7GD+%x(/y-oY
30a:-3w[9>!8y#)<%%Fl
)zmC9=2x7\c>[Us$#(i3uU28(vPM'xaA#dw%\>a$-C2Q[.>>[
,WH*>>w7T y
ax-tshV:m[2t)*$+B8D87t[Y
axw//[59q0L35dF=X0+GJ3H)cv:x=j'O5l'/<[332jw/.C/9q37j63VAobu64#Bb6
B(8YZW bV;s=5hqCP7T[
+KR->]J70# C dD\#$:-X/aS# Z9$!$S2 o9>p[S8
oQcpH$9;w%\>a$y/D;Bd\:7x(C9_*77[595AJ0[
4SqO[IV7ZU:bF2[O\;:KgzV7kS+K;G0+/ %fX4y<JWF)1-*<8
o9'xu57z,:kGZv7Gy%kxut9dq
7*u2XOgW[9>!8Y#/6K>2/0Z;y
32s$-2/:5xaA#dw%\>a$9<kO6
eOVj#K#93![7gY%KXAa#DW%\>A$\/t%fD+<6*/a9i*P!y4:da+P[
49o2XU;70d%9>!8Y#/Z=P2>6\/aCVp.#g*:ra:Z>RWi)%+L
)KD39>!8y#F:-Ga$9-w%\>a$\/ %Fd7/Xvsp\dZ[/#=-/bV07x(3/10
'\2U:KgzV7[W[n>2/b#/6K>2>6\/aC8UPh/46C[AD7%((EH+$Uqp(/Z
F8.#kC9328o#$:kGZv7Gy%kxZ..[k<N='t7% -[bH$u\()/1:l
)*T:B 2x7*D:5xaA#dw%\>a$./T'B0!G%<sC9CiY=-4(/z
F6R5w<uxu770D%9>P[s#/z=p2>6*/A:d+<6*/A9I*p!Y4:DAT0[
+)+%02X4sS3M;OL
F#X9k;D$m\q
59B([/TW0=X('.[ <W.z$M:Q
59LUD1')=bil-Y0' bV;s=5hqI1/7xe;'Q7U01;p)2LU64g)=ODI[/VSP\BU64#bB6
BU\-g\ 9mG6SHIqI-28-# o9[!$#ZW%n[ $Uq4:ra:Z>RQ
o[XAa#DW+-X 8UZ![C=2kK)b3Eu[5tJxeI:SZ<F<Ld:SZ<F.5/Bv7C7Q
o'XAa#DW+-X 8UZ![C$2kK)I5bN3JK)bL[B)Nba+HSV$)!R.5vc$)!R.BA1-*=F.BA1-;C7Q
u[XzV7\d:=028-#t%fX4y])biA1-;CF<30y23_7bLvi[P!].*/B:7<F.5[41L
T#$O)Y=rk)Phu::z=U4bat4OX+3p;][p!YPb;9H6]8
_:50*Kk)Bl[b)OX+PWi][ruA+huvk4FjXE[]kn=*RY
8xiv_7BlVtHzJA+h[*+OuA+huvknBf<(efk4F3!x9$uY])BlV -STjX3$v$,TjXMi][5c,+h(]kn=$RY
e2Zv9#9Q]>>)6ryY
ax-tshV:m[0
N7+)%f.2w##)7]=z/4T :M_0
N7eKa56(-9%==%3WJ9R$m[JY.<Jf3/L g5sKP5uh9$eK2W>(-\/ %fD7/xVSP\BU64#bB6
BU\-g\ 9mG8SHS!b1S.<9W+-XzV7\d:=02[+g/:da+$,q+HSV0
'6/9+[XzX7\;:=g289#/6K>28SH4 CVp.#g*:ra13f3r:da1,f3ry
e2Zv9#9Q=>>.4z+>cvPl
F#X9k;D$m\q
59B([/TW0=X('.[ <W.z$M:Q
59LUD1')=bil-Y0' bV;s=5hqI1/7xe;'Q7U01;p)2LU64g)==>>0%/46E0IH7).y
e0mxsW2:=>>0%/469[/$#dw+NxZ/7\2:DA+$,Q+hsv0
>=# o9[!$#ZW+-Xz[/#M-7T=,fJx#;][7r7WF)y=RK%<(EFK=x++3I]KN=$ry
8x;v_7BlVtHzJA+h[*+4F)m$/b)0cf<(ehH4c,P27z
$$1z(xVt=r=+3$/bH(<f<lD::zJr.ba1-*=f.5[$1l
T#TO)Y=rk)Phu::z=U4$D::zJr.5'][p!].ba mK7*k-7t=rk3XM81-7ir_I81-S<f<C;9:zef.5[41l
!< OBxZ[/r2Qi-0
N7+)%f.2w#8
<:e2adm#V+92F61\k!m[2WD8
<:q0>G8<'<RIwv-E2<i=)7$5sp/3Hp5d$=X0+GJ3H)q0ihs<'2c$;/92$ *dJz9*#:V]0
Z9$f%47266*$<bg;J0/U:-X $O#K:KgzV7gY%KX46_RUP6
e(77ZWZ9>!8Y#/6K>2/0Z;y
32J$o#;:kGZv7Gy%kxut9dq
7O$h$-#;:nXU$S2 o9mG6SHIq]>>$Uqri]LhP]#=-/Bt0[
4t3932V72W<9>!8Y#9q]>>)6*/a9i*P!u4:da1,.ep(7Z
F6B#F:%x!$9#/z=p2>6*/A:di[/#=-/bT07x(xD$w7X7q
7]u2X7DWZ902[O\;:ODI[/VS2K;2,_7M2Q :k7%((E*+L
)*i:-x $o#k:kGZv7Ks2k;s..G*:RA:zirwI)Y4653+x6
eI070Wo9g2/7gd+%XO..g*>C$AD7X(Xd$W7x7WF)1-(<8
o22x/$y#D:BxaA#dwUc$adH/T%Fx4Y]xT=[11$,Q+h$v0
'.uW[9P2a7ZW%n[ $\/t%f/G6SHWF)1-(<#M-7cI-=Jry
3$V$-#;:Nxu$s2 O9Mg6shiQ]>>$,Q+h$v2,_7m2q :K[
4t#932V72W<9>!8Y#9q]>>)6*/a9c*kU*'3/y23_JxwIZ
-t#dk:]diG9zD'X2g5[
,WH*>>w7T y
ax-tshV:m[2t)*$+B8D87t[Y
axw//[59q0L35dF=X0+GJ3H)cv:x=j'O5l'/<[332jw/.C/9qMg6shihB$7$kfq
Hb4/[GsWuC$ADh# [9[ $#2W+bXAa#DWi)V23_JxwIZ
 77GD+%xZx7d IB4/.1#RlVtHzJ,u$/bT0TvXp;9=,TvXp;][p!YPb7z
 57GD+%xZx7d IB4/..#RlV/[/a'2lVt=7!;<C81-(<Aihi][ruAihi]knX+L3;]knX+,b7z
o77\;:=G289# [9$ad7x(xVt4nX+,b;9H\]#=-7t=r,,+h(]5p!jup;][7R7q
$9= y])bLv -stJx3$VKNKX_(Eu+4C,+HS K4f3tX6
:2g9qrLvT=7!;_(E t0C,bi81-s<F.5/Bv7CF<3]y0
o7*;-7T=RK3xm81-7IR_i81-s<F<c;9:ZEF.5[41$.Z(XvT=R=+3$/Bh(<aM$/B)0C,UBA1-;CF<30y0
Z0\;<9mG6SHIy
ax-tshV:m[0
N7+)%f.2w##)7]=z/4T :M_0
N7eKa56(-9%==%3WJ9R$m[JY.<Jf3/L g5sKP5uh9$eK2W>(-9<KoE0IH7).y
e0mxsW2:B2uv7*P:]%2[o\;:k-a[[
4SqO[(71#/Z=P2/$#t39$h$S9/%9mG8SHS!b1S.<9S+K;23_JxeIX4y<JQ
7CDO80-f:KgzV7*U:]%2/$#/6K>2>6\/aC8UPh/46C[AD7%((EH+$Uq4(6
B(8YZW<*0 L
F#X9k;D$m\q
59B([/TW0=X('.[ <W.z$M:Q
59LUD1')=bil-Y0' bV;s=5hqI1/7xe;'Q7U01;p)2LU64g)==DIg9Zd'x2-/.cWL;Z
-/R0/.XxZ..[k<N='t70wO9G2/7GD+%xa<sGwf=AJ$u\(W/10
'03Wo9g2[O\;:K-A[7Z)<%Z
FtB#D:BxaA#dw%\>a$9<kO6
eO8=#f:%X!$9#/6K>2>6\/aC8UPh/46C[AD7%(Xr[[7]#M-7cz->7Q
7O[j$-#;:nXU$S9/%9mG8SHS!b1S.<9S+K;23_7=+A 1$Uqri=Lvk[
49+UX/$Y#d:bXA<SgWuC[AD6cK(:D+<6\/a9c*kU\'e7Xly]% 5[y0
'\\I:-X $O#K:K-A[7kS+K;GH9JIqI-G8SHWi)y485yr:ra13#,pX6
eO8<#f:%X!$9#/6K>2>6\/aC8UPh/46C[AD7%(Xr[[7]#M-7cz->7Q
7O[Y$-#;:nXU$S9/%9mG8SHS!b1S.<9S+K;23_7=+A 1$Uqri=Lvk[
49+$X/$Y#d:bXA<SgWuC[AD6cK(:D+<6\/a9c*kU\'e7Xly]% 5[y0
'\\l:-X $O#K:K-A[7kS+K;GH9JIqI-G8SHWi)y485yr:ra13#,pX6
B(8YZW+C$;/92$ *Z
[$!</AmxD8[
,WH*>>w7T :*eIg#Z#0=Xd [
,W=b;;:0eKFrL X5sKP5uh9$/4(- :-Y[' bV;s=5h=b$7[0e9q=>>.<9x<]82RC8
X<03aM%#9Q=>>.<9w+%xZA7\k:kGZv7x(p9I*p!Y4Y
o 28y# z9[u$s2 O9[ad7x(xVt4nX+,b;9H\]#=-7t=r,,+h(]5p!jPp;][7R7q
$9= y])bLv -stJx3$VKNKX_(Eu+4C,+HS K4f3tX6
:2g9qrLvT=7!;_(E t0C,bi81-s<F.5/Bv7CF<3]y0
o7*;-7T=RK3xm81-7IR_i81-s<F<c;9:ZEF.5[41$.Z(XvT=R=+3$/Bh(<aM$/B)0C,UBA1-;CF<30y0
Z0\;<9mG8SHSP\Z
[$!</AmxD8[
,WH*>>w7T :*eIg#Z#0=Xd [
,W=b;;:0eKFrL X5sKP5uh9$/4(- :-Y[' bV;s=5h=b$7[0e9q]>>.<9x<]82RC8
X<03aM%#9Q]>>.<9w+%xZA7\k:kGZv7Gy%kx4Y<#=-/bV0[
Dp:KgzV7gY%KX 8UZ![C=2kK)b3Eu[5tJxeI:SZ<F<Ld:SZ<F.5/Bv7C7Q
o'XAa#DW%\>A$Y\M<03G677bL:9U_8sbLvThZj,U$/Bv0tVxP;9=,tVxP;][P!ypB;][P!].X6
mh$#DW+nXz/7gY%KXI[/#M-7T=,fJx#;][7r7WF)y=RK%<(EFK=x++3I]KN=$ry
8x;v_7BlVtHzJA+h[*+4F)m$/b)0cf<(ehH4c,P27z
$$1z(xVt=r=+3$/bH(<f<lD::zJr.ba1-*=f.5[$1l
T#TO)Y=rk)Phu::z=U4$D::zJr.5'][p!].ba mK7*k-7t=rk3XM81-7ir_I81-S<f<C;9:zef.5[41l
!< OBxo..G*Qi-0
N7+)%f.2w#8
<:e2adm#V+92F61\k!m[2WD8
<:q0>G8<'<RIwv-E2<i=)7$5sp/3Hp5d$=X0+GJ3H)q0ihs<'OcG3/6:5hB$7$kfq
Hb4/[GsWoCg3/6:5:O8z\9#tF002 _3W'Y2;y=JWi)%0
V6:Mo9$l\9#9!=4U$Y/d;bD\,Y#rL56(gfJxe[]1L
y/D;9$L\9#9!=4u$y/T+i12Kk)Bl56(G5x.5u]$rk)m$u][Sc,[b;9:z>3.x6
PG:09WuW[M/7*=RbX .O'KqY2p$])$;*=[P!ypB7Z
-t#dk:%d!:9/[;6
92Z0g*09.zL
F#X9k;D$m\w93$;89CV+9.\l
F#'<F=3t5z=fqp/-%z4'u y96r+[[1wv1E2<i=)7$5'<]8at5G2;RUH9$+k2wx=4[
+KR->]J7g2;ruh9$#fZ[XU$9\p:b$h$S2 o9>p[S8
oQc2uv=#/z=p28(5iCsxa<sGw%\>a$s9/%9Mg8shs!B1s.<9s+k;23_jXEix4Y<jq
7CD(/Y-W%n[ $#(h>U 28(5Im[Xz2$VUe9>p[S#9q=>>.4Z+>CVp.#g*:ra:Z>RWi)V:L
)/s9Bp)$s2 O9>!8y#/z=p28(5iM[xa<sGwUc[ad6Ck(:d+<6\/A9I*p!Y4:DA+p[
4Sq*0 :=#K:=5Y)j3W%n[ $8/ i*il$8qUcIX3,_3I:r8z[_JWiW[Ay$8
o!=-H$#(H>u 28(U+MsxaA#dw%\>a$4\yp\x48_3+(9CiY=j+Y
38Z<J#kC90+$s2 O9>P[s##+\vP$u\(3/12,.QPM/z
Fh#9i:B%2/#3w%N[ $s9/%98Z<<9wI]AHSX#m+) :p[
4#+\V2/<#K2[XAa#DW%\>A$4\YP\X48_y+:d$*7=JQ
7W[p9$# s$1)*7\Cw//:$S2 o9>p[S##+\Vp$U*(w/X48_3+(6
e78+5j:=5tPhJW<'XAa#DW%\>A$4\YP\X48_u4:d$*7<JQ
7=PhP70d390I77gd+%XAa#DWuC[AD6\/a9i*P!y4:dahP[
4 o'XU;7Zt39>p[S#/Z=P2[+g/:ODI[//t%fXlyx+lP9c*0[
4 o2X/a=#K2[XU;7gd+%XA<SgWuC$AD6*/a9c*07%((EH+L
!< OBxaj8%332j0
N7+)%f.2w#8
<:e2adm#V+92F61\k!m[2WD8
<:q0>G8<'<RIwv-E2<i=)7$5sp/3Hp5d$=X0+GJ3H)q0ihs<'Uc[ad!zT!9tkl
!z![k,'$\/ %FxZv7\D:=02[o\;:DA+$,Q+h$v0
>=# o9[!$#ZW%n[ $#g*:da1RKX<(EFK4f3!X9i*kK)bFA1-;C.+H/%+4C,pR7Z
$$1d(xVt=r=+3$/bH(<f<lD::zJr.ba1-*=f.5[$1l
T#$<)Y=rk)Phu::z=U4bat4OX+3p;][p!YPb;9H6]8
_:]p*Kk)Bl[b)OX+PWi:4OX+3p;9J4FjX#;][7R7w2BA1rk)B3eU$p!3Jp8C$p!;4ba%knX+,b;9H\]8
X9=pu$\/ %Fz
[$!</AmxD8[
,WH*>>w7T :*eIg#Z#0=Xd [
,W=b;;:0eKFrL X5sKP5uh9$/4(- :-Y[' bV;s=5h=b$7[0e9q]>>Z9*#:v]0
Z9$f%472>6*/a9[ $#2W+bXAa#DW%\>A$Uq4:ra:ZIRQ
o[XAa#DW%\>A$Y\M<03Gg77bLv -sf-_(E*+oh+4BAT4oh+4B;9:Z>3.X6
Pj$S2 o9>p[S#;+d0MX6*WXvTSN9_5 vT=R=+35'::ZIR_>EVKNKX_>EVK4fJxe[]K4fJx#;y0
>=# o9[!$#ZW%\>A$.g*:da1RKX<(EFK4f3!X9i*kK)bFA1-;C.+H/%+4C,pR7Z
$$1d(xVt=r=+3$/bH(<f<lD::zJr.ba1-*=f.5[$1l
T#$<)Y=rk)Phu::z=U4bat4OX+3p;][p!YPb;9H6]8
_:]p*Kk)Bl[b)OX+PWi:4OX+3p;9J4FjX#;][7R7w2BA1rk)B3eU$p!3Jp8C$p!;4ba%knX+,b;9H\]8
X9=pu$\/T%Fz
[$!</AmxD8[
,WH*>>w7T :*eIg#Z#0=Xd [
,W=b;;:0eKFrL X5sKP5uh9$/4(- :-Y[' bV;s=5h=b$7[0e#+\VpZ9*#:v]0
Z9$f%472H#94698z$M$2:KgzV7gY%KX46_;+:d[*7x8
oQcMZ77t! 98Z$s2 O9>!8y#9Q=>>.<9s+k;23_jXEix4Y]x 5[Y0
'6/92[Xd\%##+9>p[S#/Z=P2[+g/:ODI[//46C$AD7%((EH+$Uqri]9hk[
+)+%02H#9466
92Z0g*09.zL
F#X9k;D$m\w93$;89CV+9.\l
F#'<F=3t5z=fqp/-%z4'u y96r+[[1wv1E2<i=)7$5'<]8at5's+D2L3!zT!9tkl
!z![k,'$8/ I*IL$/CDA9ID,7GD+%xLh#G(p9C78sQ+:yC*07'(34z
-61'$U9$:Y])5I!b:5BfRY
% 2[o\;:R.4$y\m<03gG[
aWXvT=R.J<Lv655f)UP$L=R8X6H/%j4f+,B;]W)bJ.$I:lH#g_iW[A4f)5i8c78SF.=U][P!ypB7Z
-61'$U9$HY])5I!b:5BfRY
%%2[o\;:F8!d7d IB4/.18
_:7t=rk*P5Vt3=B,BCi*wrk'm*e1J5c,X#;]k-H-+b8v$34\/$D8Z[c,B;D:4h#G.bqUknX+L3;Y0
Z.[5'OXI5_7bcQuKk[
D3:KgzV7%vi9Pz,9$fq]Z
$$])TCat3,Tx#+k:=rk'6CatJ0iEBlyC5zX-ubabe4cf'>'1knk'm*e1J5cf_p8I78sAm!=>knX+,b7z
-61'$U9$)Y])u=u]1l
yvw%N[ $/CDA9pZ,9$FQ]z
$$])TMat3,Tx#+k:=rk'6CatJ0iEBlyC5zX-ubabe4cf'>'1knk'm*e1J5cf_p8I78sAm!=>knX+,b7z
3x7zP:B%2Kk'6l'9=5<U'lV64nX+,b!1-pBf.b;Y2/s[=9) -perw k *5!vP9!1)l
T#2%'Aez$r)*/j0
:/3WaWg>$93WXv%+(5)b;d9:ZEF6(E1j4C7W<K=lT_3x((V2JS3(3EH+T3J3:x>jy<+,(*\:9[
'*c90j$,TM:7Tj0IebLYc[P!].*/B:5CFr:b>;30qpH/F+$%gp-[Bv00.+m97A5_Rx#/25P$8
X9=pu$8/ I*ILl
F#X9k;D$m\q
59B([/TW0=X('.[ <W.z$M:Q
59LUD1')=bil-Y0' bV;s=5hqI1/7xe;'Q7U01;p)2LU64g)=%Dz,!Zt!9TKL
!z![k,'$y/ I9M78Rzw2R4u$s2 O9=3t1QP(6
Ph$.%!<9m78rZWoC$z0x#rL56(gfJxe[]1L
y-w%N[ $\C rBx 8uz![c=2Kk)$;*=[5!r.5/bV7c7q
oUXAa#DWuW[M/7D ib4/..#rLv/[R9_5 v=3T1,UHI]K4fJx#;y0
Z0\;<9PG8U8
<:e2adm#V+6
92Z0g*09.z$04t'=07w##vT6
92-9H$;*LU3,e;[Q7U01;p)2D+P-3+=%=WJ9R$m[JY-9*#%*LA<SgS3'1:.bJ+qIeAZ9*#:v]0
Z9$f%472[+g/q[%:P6-+(CVf[7*$o9>!8Y8
oQcMZ77*m[9$;v7zP:kGZv7\2[9[ad<Ssp\dZ[/#=-/bV07x(3'1:l
)/sU=%26u0w25p2/=#TI-xZj-# %Fv'.<9s+k;23_jXEix4YBj+Y
3dg>#;w2D32/=#T'%xu77\2[9[ad<Ssp\dZ[/#=-[U-97x(3/bT0[
4SqY 2/=#Kc9>!8Y#5q=c(3,#M!=>*P7%#+Ka:$8qImUu2:Uq4y
3dg:B#TI-xaA#dw%N[ $8/ I*IL$uC %)1234\/-/x3Y=]i:yC*7$8
oQc6)$#SF:kGZv7GD+%x3.#x)fRx4h#G((9I78sQ+:yC*7$#5-[fsl
)/s;:xu57GD+%xaA#dw;c[4t,%w;DA+$uC %)1234\/-/x3YH;3M6
B(8YZW%\>A.=-+(C%:P6RO%6
92Z0g*09.zL
F#X9k;D$m\w93$;89CV+9.\l
F#'<F=3t5z=fqp/-%z4'u y96r+[[1wv1E2<i=)7$5'<]8at5<kO'E-/.Cwl;z
-/R0/.Xx(/y-o:]= $s2 O6
Ph$S2 o9$;V7DS2=V:$])bP(B+Nb+4BABv7C7Q
o'XAa#DW25P2V#XKR-D;$b-336
P)$S2 o9$;V7D ib4/..#UcUZ
F.6K 390H$9vw%N[ $s2 O9Mg8shsp\dZ[/#=-/bV07x(3s10
'6/535XU)7gd+%XAa#DW;C[4T,%WiW[Ayx#=!=>*07'(>2J2:Uq4H$V0
'6/53-XU)7gd+%XAa#DW;C[4T,%WiW[Ayx#=!=>*07'M-IBt07'(>2J0
:b#t'%XU77V+:b>;30qpH/F+$%gp-'BS70.+m97A5_]x)I25P$8
X9=pu$0z;C3z
[$!</AmxD8[
,<y
a92j/<wtmILWuC z9bu\-G\ Bx4t8<w'%p(v70::X;($s%)'=23$st9U5[ z[
,<:x;(/0#$;*X3TA$#;*P2H##v;%23$%TW;*md<0#2a*XU64g)qO. T,#t'Y=OT%<5<EZ
[n[
,WuMP7 4<;:x;($\/t%fD+<7\) r8UJ7:v;97>T7*/a90IHS<WuMP(3!+xy
e0mxsW2:odi[//46c$ad7\;:=G289#/z=p2[+G/:DA+$,Q+hsv0
V=#/Z=P2[+g/:%[4/r0S'9y=RK3xmA%$P!y4$:B+4f)M$:B+4C,+HS Kk[
DU:KgzV7gY%KX 8UZ![C$2kK)I5bN3JK)bL[B)Nba+HSV$)!R.5vc$)!R.BA1-*=F.BA1-;C7Q
u[XzV7\d:=02[+g/:]>>$UqrLvc[P!].BA Mk7%(XvT=3fJx#;\:Zx34B;9h\]8
_:5p*Kk)Bl[b)OX+PWi][ruA+huvk4FjXE[]kn=*RY
8x;/_7BlVtHzJA+h[*+4F)m$/b)0cf<(ehH4c,P27z
$$.d(xVt=r=+3$/bH(<Am$/b)0c,uba1-;cf<30Y269QRlVt=7!;_(e T0Tx_(eU+4F-.5/be4c,Pr7z
-t#dk:odi[//46c$ad[
,WuMP7 4<;:x;($\/ %fXzT%%#<xX\w8#2a*Xz[/#K2W>($\T;9rB-Z[
+KR->]J7kS+K;G8SHW+%Xza7\K:KgzV7X(P9i*P!u4y
o 28y# z9[u$s2 O9[ad7x(xVt4nX+,b;9H\]#=-7t=r,,+h(]5p!jup;][7R7q
$9= y])bLv -stJx3$VKNKX_(Eu+4C,+HS K4f3tX6
:2g9qrLvT=7!;_(E t0C,bi81-s<F.5/Bv7CF<3]y0
o7*;-7T=RK3xm81-7IR_i81-s<F<c;9:ZEF.5[41$.Z(XvT=R=+3$/Bh(<aM$/B)0C,UBA1-;CF<30y0
Z0\;<9mG8SHS+K;0
N7kvoW_7TY#2a*XO.#g*qW0:)6RY:=2'34Z2:j.3$%H):=>>$9*#%*XOwY<=HEB0
Z9$f%472>6\/aC8UPh/46C[AD7\f:=P28O# <9>p[S#M-IXlyx+lP6
eG.\\p:=328Y# Z9[U$S9/%9[AD<sSP\Dz[/#=-7i[7]#M-7c[7]8
X9=pu$\/ %Fd7/Xvsp\dZ[/8
<:o. hDC)O97>t7Ks2k;s$#<2fw0'$Dt5:X;($.G*:B$7[0#90%2Lz!+q
Hb4/[GsWuC$ADh/t%fXzX7\;:=g289#/Z=P2,_RWF)1-(<8
;39>!8y# [9pZ,9$FQ5x1rk)Phu9JOX+Jp8/-0c,BI8/-0cf<(ehH4]8
;C9>!8y# [9pZ,9$FQ]x1rkv<<>6'rk)B3eU[5TjXWi:sz<f<lD:sz<f.5/bV7cf.5/be4]8
939[ $#2w+BxZx7*/A9C*Kk)m5/be4c,Pr7xLY])BlR9:zef6(e1J0cf<30Y0
o7[;-7T=RK3xm81-7IR.5vc$P!;4B;9:Z>3.BA Ik[
aW'ba1RK)b3Eu$P!3jP;9=,tJxmI]KNx+l3;][7.7Q
$9$ y])bLv -stJx3$V$,tJxmI][5C,+H(]KN=$r:]0*kK)bL[B)ox+pwI:4ox+3P;9j4fJx#;][7r7Q
H*[ /7kS2K;S..g*y
axoWyC[!*p2j/<wUc[ad6ry:=2'34z2:J.3$%h):=>>$9*#%*xoWy<=heb0
Z9$f%472>6\/aCVp.#g*:=P28O# <9>!8Y#M-IXlyx+lP6
mh$#DW+nXz/7gd+%Xz[/#M-7T=,fJx#;][7r7WF)y=RK%<(EFK=x++3I]KN=$ry
8x;v_7BlVtHzJA+h[*+4F)m$/b)0cf<(ehH4c,P27z
$$1z(xVt=r=+3$/bH(<f<lD::zJr.ba1-*=f.5[$1l
T#TO)Y=rk)Phu::z=U4$D::zJr.5'][p!].ba mK7*k-7t=rk3XM81-7ir_I81-S<f<C;9:zef.5[41l
!< OBxo.#G*Qi-g8shq
59mdV4:#9%X'D0#9q]>>$#<2FW0'$dT5:x;($.g*:b$7[0#90%2lZ!+Q
Hb4/[GsWuC$AD6*/a9[ $#2W+bXAa#DW%\>A$Uq4:ra:ZIRQ
o[XAa#DW%\>A$Y\M<03Gg77bLv -sf-_(E*+oh+4BAT4oh+4B;9:Z>3.X6
Pj$S2 o9>p[S#;+d0MX6*WXvTSN9_5 vT=R=+35'::ZIR_>EVKNKX_>EVK4fJxe[]K4fJx#;y0
>=# o9[!$#ZW%\>A$.g*:da1RKX<(EFK4f3!X9i*kK)bFA1-;C.+H/%+4C,pR7Z
$$1d(xVt=r=+3$/bH(<f<lD::zJr.ba1-*=f.5[$1l
T#$<)Y=rk)Phu::z=U4bat4OX+3p;][p!YPb;9H6]8
_:]p*Kk)Bl[b)OX+PWi:4OX+3p;9J4FjX#;][7R7w2BA1rk)B3eU$p!3Jp8C$p!;4ba%knX+,b;9H\]8
X9=pu$\/T%Fdi[/8
<:o. hDC)O97>t7Ks2k;s.<9w+*7Lh9Swtm62j/<w2k;2/.C/99MDv0%Xhez
-/R0/.Xxo..G*>cvP..G*:=328y# z9[u$s2 O9C*07%((eh+l
y3w%N[ $#0wO=Cu\-/$:7t=r=+35'::z>r_>evknkx_>evk4FjXE[]1l
y-w%N[ $#0wO=Cu\-/T:7t=)Fz%;Xt=rk3XMa%$p!Y4$:b+4F)m$:b+4c,+hs k4c,+h(]1l
\3w+%xZA7\k:=326shwI)Y=ru,+h(]kn=$R:RA1rk)=5/be43jX([vk4F3!x6
:2gYqrLvT=7!;_(E t0C,bi81-s<F.5/Bv7CF<3]y0
o7[K-7T=RK3xm81-7IR.5vc$P!;4B;9:Z>3.BA Ik[
aW2%a1RK)b3Eu$P!3jP8c$P!;4BA%KNx+,B;9h\]#t<)y=RK)pHU::Z=u4$d::ZjR.5'][P!].BA Mk[
+)+%02>6*/a:D+<6*/a6
92>MD#TW2 $%H):%Dz,7\) r8UJ7:v;97>T7DS2=%+P7Zt!K22>MD)FEB-L
!z![k,'$y/ Icpg6#-4(9M78Rzw2R4u$s2 O9=3t1QP(6
Ph$.%!<9m78rZWoC$z5<JWXv=3T1,+HS Kk[
DU:KgzV7k#+002V#XKR-D;$])b'Y2;Nb+4BA1-*=Fry
%U2[o\;:o8Z\9#;+D0mx6*wxVtsnkz%;Xt;:0[<Cevk4c,+h(]1l
!< OBx .#xsOc$Z5<jq
59mdV4:#9%X'D0#;q=c280s=!b72 M'W f22V6* P/XU64g):O. T,+xH6
BU\-g\ 9PG8U/;q][+P7k#+0026,$K:KgzV7[595ahP[
Dp:]iM/7k#+002V6* P/X1R1')'A1-*=Fry
%%2[o\;:o8Z\9#;+D0mx6[wxVt;:0[<CevknX+L3;Y0
Vj#/Z=P2>4\!<9Pz,9$fq]X1RKV<LbN3JK[5959jZ<F.BA1-;C7Q
H*[ /7DS+dD ..\4(6
92>MD#TW2 $%H):=>>0%/469[(J,cK 9_d:7s*99[AD7Zt!K22>MD)FEB-L
!z![k,'$#G*pXd+<6\/A9[/$#dw+NxZ/7\2:DA+$,Q+hsv0
>=# o9[!$#ZW+-Xz[/#M-7T=,fJx#;][7r7WF)y=RK%<(EFK=x++3I]KN=$ry
8x;v_7BlVtHzJA+h[*+4F)m$/b)0cf<(ehH4c,P27z
$$1z(xVt=r=+3$/bH(<f<lD::zJr.ba1-*=f.5[$1l
T#TO)Y=rk)Phu::z=U4$D::zJr.5'][p!].ba mK7*k-7t=rk3XM81-7ir_I81-S<f<C;9:zef.5[41l
!< OBxZ[/r2Qi-g8shq
H0[I:MsQ
.ENDS TS5A3166
