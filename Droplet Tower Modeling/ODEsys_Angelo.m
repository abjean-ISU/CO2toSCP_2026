function dydx = ODEsys_Angelo(x,y,r,constants)
%inputs
%x: position 
%y[v,c,t]
%v: velocity (m/s) v(0)=Q/A
%c: concentration (g/L) c(0)=0
%t: time (s) t(0)=0
%r: droplet radius (m)

%constants 
Csat = constants(1); %saturation concentration (g/L)
g = constants(2); %acceleration due to gravity (m/s2)
rho_g = constants(3); %density of air (kg/m3)
rho_l = constants(4); %density of water (kg/m3) 
mu_g = constants(5); %viscocity of air (m2/s)
DAB = constants(6); %diffusion coefficient of CO2 in water at 25C (m2/s)
s_tension = constants(7); %water surface tenstion (g/s2)

%dynamic values 
Re = 2*rho_g*y(1)*r/mu_g; %Reynold's Number 
a = 3/r; %surface area to volume ratio 1/m
tau_osc = (pi/4)*sqrt(((rho_l*1000)*((2*r)^3))/s_tension); %oscillation timescale (s)
kL = 2*sqrt(DAB/(pi*tau_osc)); %mass transfer coefficient m/s

Gv = g - (9/2)*(mu_g/(r^2*rho_l))*y(1)*(1+0.158*Re^(2/3)); %acceleration (m/s2)
Gc = kL*a*(Csat-y(2)); %rate of change of concentration (g/L/s)

%system of odes 
dydx(1,:) = Gv./y(1); %dvdx velocity ode (1/s)
dydx(2,:) = Gc./y(1); %dcdx concentration ode (g/L/m)
dydx(3,:) = 1./y(1); %time (s/m)

end


