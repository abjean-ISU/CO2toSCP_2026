clear all;close all;clc;

%CO2 droplet tower model 

%USER INPUTS---------------------------------------------------------------

%Import droplet size data OR Designate mean droplet diameter (mm) - 
% select relavent input
%DropletSize = readmatrix(['C:\Users\anbarron\Box\Research\Projects\SCP\Modeling\Droplet Tower Modeling\DropletDiameterData.csv']); %droplet diameter data (mm) 
DropletSize = 1.6; %mean droplet diameter (mm)

%Input Tower Parameters 
towerHeight = 4; %m
towerDiameter = 10; %m 

%Input manifold parameters
d_orifice = 0.8/1000; %droplet manifold orifice diameter (m)
N_o = 30790750; %number of orifices in droplet manifold 

%Input operating conditions 
Q = 11.5; %liquid flowrate (m3/s)
T = 30+273.15; %liquid temperature (K)
P = 0.1; %operating (headspace) pressure (atm) 

%Input relavelt gas composition information 
DAB = 1.67E-9; %diffusion coefficient of gas in water at correct Temp (m2/s)
H = (1/(exp(-159.854+8741.68/T+21.6694*log(T)-1.10261E-3*T)))/55342; %Henry's Constant for CO2 (atm-m3/mol)
c0 = 0.0; %initial dissolved gas concentration (g/L)
mass_Gas = 44.01; %relavent gas molar mass (g/mol)

%END USER INPUTS ----------------------------------------------------------

%Determining weights and abscissae for droplet size distribution
if size(DropletSize)  == 1
    GQMOM_model_x = DropletSize/1000/2; %convert mean drop diameter to radius (m)
    GQMOM_model_w = 1; %using only 1 abscissae
else 
    %normalizing diameters against maximum diameter 
    diameter_max = max(DropletSize);
    diameter_norm = DropletSize./diameter_max;

    %computing the histogram and moments
    [hist_weights,edges] = histcounts(diameter_norm,20,'Normalization','probability');
    hist_abscissae = edges(1:end-1)+ diff(edges)/2;
    for i = 0:10
        calc = hist_weights.*(hist_abscissae.^i);
        hist_moments(i+1) = sum(calc);
    end

    %Using GQMOM with 4 abscissae to determine ODEs 
    [GQMOM_model_w,GQMOM_model_x,GQMOM_model_werror]=PD_gqmom_0_1(hist_moments,floor(length(hist_moments)/2-1),4);

    %converting x to radii in m
    GQMOM_model_x = GQMOM_model_x*diameter_max/2/1000; %m
end

%Computing initial system parameters
%height
xspan = 0:0.01:towerHeight; %location (m)
%velocity 
A_orifice = pi*(d_orifice/2)^2*N_o; %cross sectional orifice area (m2)
v0 = Q/A_orifice; %initial droplet velocity (m/s)
%time
t0 = 0; %inital time (s)
%intial conditions vector
y0 = [v0,c0,t0];

%Constant parameters 
Csat = P/H*mass_Gas/1000; %g/L
Csat = 0.85*Csat; %adjusting for mineral media
g = 9.8; %acceleration due to gravity (m/s2)
rho_g = 1.184; %density of air (kg/m3)
rho_l = 997; %density of water (kg/m3) 
mu_g = 1.53E-5; %viscocity of air (m2/s)
DAB = DAB; %diffusion coefficient (m2/s)
s_tension = 72.8; %water surface tenstion (g/s2)

constants = [Csat, g, rho_g,rho_l,mu_g,DAB,s_tension]; 

%Gas absorption modeling <v(x|r)> and <c(x|r)> using kL model by Angelo et al.
for i=1:length(GQMOM_model_x)
    [x_angelo,y_angelo] = ode45(@(x,y) ODEsys_Angelo(x,y,GQMOM_model_x(i),constants), xspan, y0);
    v_angelo_ri(:,i) = y_angelo(:,1);
    c_angelo_ri(:,i) = y_angelo(:,2);
    t_angelo_ri(:,i) = y_angelo(:,3);
    v_angelo_ri_weighted(:,i) = v_angelo_ri(:,i)*GQMOM_model_w(i);
    c_angelo_ri_weighted(:,i) = c_angelo_ri(:,i)*GQMOM_model_w(i);
    t_angelo_ri_weighted(:,i) = t_angelo_ri(:,i)*GQMOM_model_w(i);
end

%Modeling <v(x)> and <c(x)> using weights
v_x = sum(v_angelo_ri_weighted,2);
c_x = sum(c_angelo_ri_weighted,2);
t_x = sum(t_angelo_ri_weighted,2);

%system parameters 
tower_v_tot = pi*(towerDiameter/2)^2*towerHeight; %tower volume (m3)

%droplet parameters
droplet_r = sum(GQMOM_model_x.*GQMOM_model_w); %average droplet radius (m)
droplet_v = 4/3*pi*droplet_r^3; %average droplet volume (m3)

%Liquid holdup parameters
droplet_v_tot_m3 = Q*max(t_x); %total droplet (LH) volume (m3)
droplet_v_tot_L = 1000*droplet_v_tot_m3; %total droplet (LH) volume (L)
N_tot = droplet_v_tot_m3/droplet_v; %total number of droplets
droplet_density_tot = N_tot/tower_v_tot; %total droplet number density (droplets/m3)
liquid_holdup_tot = droplet_v_tot_m3/tower_v_tot; %total liquid holdup (unitless)

%overall column performance 
kLa_L= (1/max(t_x))*log((Csat-c0)/(Csat-max(c_x))); %kLa (1/s) on a liquid volume basis
kLa_T = kLa_L*liquid_holdup_tot; %kLa (1/s) on a total volume basis
