clear all;close all;clc;

%H2 tower model  

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
N_o = 1539538; %number of orifices in droplet manifold 

%Input operating conditions 
Q = 5.77E-01; %liquid flowrate (m3/s)
T = 30+273.15; %liquid temperature (K)
P = 4; %operating (headspace) pressure (atm) 

%Input relavelt gas composition information 
DAB = 4.58E-9; %diffusion coefficient of gas in water at correct Temp (m2/s)
H = (1/(exp(-125.939+5528.45/T+16.8893*log(T)-0E-3*T)))/55342; %Henry's Constant for gas (atm-m3/mol)
c0 = 0; %initial dissolved gas concentration (g/L)
mass_Gas = 2; %relavent gas molar mass (g/mol)

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
R_gas = 8.314462; %J/mol-K
rho_g = P*101325*(mass_Gas/1000)/(R_gas*T); %ideal-gas density of the tower gas (kg/m3)
mu_g  = 9E-6;  %dynamic viscosity of the tower gas at T (Pa s)
rho_l = 997; %density of water (kg/m3) 
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

%volume-weighted (mixing-cup) averages for concentration and residence time
volW = GQMOM_model_w(:).*GQMOM_model_x(:).^3; volW = volW/sum(volW); %liquid volume fraction per size
v_x = sum(v_angelo_ri_weighted,2);   %number-weighted mean droplet velocity (unchanged)
c_x = c_angelo_ri*volW;              %outlet concentration of the collected liquid (g/L)
t_x = t_angelo_ri*volW;              %volume-weighted residence time (s)

%system parameters 
tower_v_tot = pi*(towerDiameter/2)^2*towerHeight; %tower volume (m3)

%droplet parameters
droplet_v = sum(GQMOM_model_w(:).*(4/3)*pi.*GQMOM_model_x(:).^3); %mean droplet volume (m3), Eq. 24

%Liquid holdup parameters
droplet_v_tot_m3 = Q*max(t_x); %total droplet (LH) volume (m3)
droplet_v_tot_L = 1000*droplet_v_tot_m3; %total droplet (LH) volume (L)
N_tot = droplet_v_tot_m3/droplet_v; %total number of droplets
droplet_density_tot = N_tot/tower_v_tot; %total droplet number density (droplets/m3)
liquid_holdup_tot = droplet_v_tot_m3/tower_v_tot; %total liquid holdup (unitless)

%overall column performance 
kLa_L= (1/max(t_x))*log((Csat-c0)/(Csat-max(c_x))); %kLa (1/s) on a liquid volume basis
kLa_T = kLa_L*liquid_holdup_tot; %kLa (1/s) on a total volume basis
