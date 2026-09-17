function [w,x,werror] = PD_gqmom_0_1(mom,N,Nnode)
% GQMOM for 2N+1 moments on (0,1)
% Nnode quadrature using product difference algorithm

%inputs
% mom: moment vector from order 0 to 2n [M0 M1 M2 ... M2n] 
% N: number of moment nodes to be used in alorithm
%   maximum possible number of nodes = length(mom)/2-1
%Nnode: total number of w and x nodes to be computed; arbitrarily high

%outputs
% x are abscissas 1:Nnode
% w are weights 1:Nnode
% werror > 0 when algorithm fails due to unrealizable moments
%

if Nnode < N
    Nnode = N;
end

werror = 0 ;
w = zeros(Nnode,1) ; 
x = zeros(Nnode,1) ; 

% PD algorithm to find zeta_k coefficients up to 2N
p = zeros(2*N+1,2*N+2);
p(1,1)= 1;
for i = 1:2*N+1
    p(i,2)=(-1)^(i-1)*mom(i)/mom(1);
end
for j = 3:2*N+2
    for i = 1:2*N+3-j
        p(i,j)=p(1,j-1)*p(i+1,j-2)-p(1,j-2)*p(i+1,j-1);
    end
end

%
zeta = zeros(2*Nnode+3,1);
zeta(1) = 0;
for i = 2:2*N+1
    if p(1,i)*p(1,i-1)>0
        zeta(i)=p(1,i+1)/(p(1,i)*p(1,i-1));
    else
        zeta(i)=0;
        disp('zeta = 0')
        disp(p)
    end
end

%
pp = zeros(2*Nnode+1,1);
pp(1) = 0;
for i=2:2*N+1
    pp(i) = zeta(i)/(1-pp(i-1));
end
%%%%%%%%%%%%%%%%%%
% closure for p
for i=2*N+1:2:2*Nnode+1
    pp(i+1) = pp(i-1);
    pp(i+2) = pp(i);
end
%disp(pp)
%%%%%%%%%%%%%%%%%%
% closure for zeta 
for i = 2*N+2:2*Nnode+3
	zeta(i) = pp(i)*(1-pp(i-1)) ;
end

%%%%%%%%%%%%%%%%%%
a = zeros(Nnode,1);
b = zeros(Nnode,1);
for i = 1:Nnode+1
    a(i)=zeta(2*i)+zeta(2*i-1);
end
for i = 2:Nnode+1
    b(i)=zeta(2*i-1)*zeta(2*i-2);
end
% disp(a)
% disp(b)
% disp(zeta)
% Check if moments are realizable
zetamin = min(zeta(2:end)) ;
zetamax = max(zeta(2:end)) ;
%
if ( zetamin <= 0 || zetamax >= 1 )
    disp('Moments in PD_gqmom are not realizable!')
    disp(zeta)
    werror = 1 ;
    %return
end
%
% Setup Jacobi matrix to find roots of Q_{Nnode}
z = zeros(Nnode,Nnode) ;
for i = 1:Nnode-1
    z(i,i) = a(i) ;
    z(i,i+1) = sqrt(b(i+1)) ;
    z(i+1,i) = z(i,i+1) ;
end
z(Nnode,Nnode) = a(Nnode) ;
%
% Compute weights and abscissas
[eigenvector,eigenvalue] = eig(z) ;
%
for i=1:Nnode
    w(i)= mom(1)*eigenvector(1,i)^2 ;
    x(i)= eigenvalue(i,i) ;
end
end