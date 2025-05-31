
.. _`sec:ESIBD`:

Electrospray ion-beam deposition
================================

In electrospray ion-beam deposition (ESIBD, also known as soft/reactive
landing or preparative mass spectrometry), molecules (small molecules, glycans, peptides, proteins, viruses, ...) are transferred
from solution to the gas-phase using electrospray ionization to form
intense (if required *m/z*-filtered) molecular ion beams, which are then
deposited with well defined energy onto various surfaces in vacuum.\ :cite:`johnson_soft-_2016, cyriac_low-energy_2012, krumbein_fast_2021`
It has been successfully enabling high-resolution imaging of complex
molecules by scanning probe microscopy,\ :cite:`hamann_ultrahigh_2011,rauschenbach_mass_2016,abb_two-dimensional_2016,deng_close_2012,rinke_active_2014,wu_imaging_2020,fremdling_preparative_2022`
transmission electron microscopy,\ :cite:`mikhailov_mass-selective_2014,prabhakaran_rational_2016,vats_electron_2018`
cryo-EM,\ :cite:`esser_mass-selective_2022,esser_cryo-em_2022`
and low-energy electron holography.\ :cite:`longchamp_imaging_2017,ochner_low-energy_2021,ochner_electrospray_2023`
These experiments show that individual peptides, glycans, and proteins
can be isolated from a mixture, separated from solvent and contaminants,
deposited, and imaged. The ESIBD approach to sample fabrication has
been used to address fundamental questions related to gas-phase structures,\ :cite:`ochner_low-energy_2021`
mechanical properties,\ :cite:`anggara_exploring_2020,rinke_active_2014`
and substrate interactions,\ :cite:`volny_preparative_2005`
by direct observation of deformation,\ :cite:`rinke_active_2014,anggara_exploring_2020`
fragmentation,\ :cite:`rinke_active_2014,krumbein_fast_2021`
and assembly at surfaces depending on ion-beam composition,\ :cite:`abb_two-dimensional_2016`
substrate,\ :cite:`deng_close_2012`
and landing energy.\ :cite:`ochner_low-energy_2021,rauschenbach_electrospray_2009`

.. _`fig:setup`:
.. figure:: 2023-10_ESIBD_Setup.png

   **Overview of the Oxford ESIBD setup.** Colored boxes highlight selected
   hardware that is controlled by ESIBD Explorer plugins. **Left** :blue:`ESIBD Explorer`,
   :green:`current measurement` (RBD 9103), :red:`voltage supplies and distribution`
   (ISEG ECH 244, ISEG EBS 180 05). **Right** Custom :purple:`deposition stage`,
   independently controlled :orange:`commercial mass spectrometer`
   (Thermo Scientific :sup:`TM` Q Exactive :sup:`TM` UHMR instrument),
   :darkblue:`temperature measurement` (Sunpower CryoTel GTLT), :darkorange:`pressure measurement`
   (Edwards TIC, Pfeiffer TPG366). See references for more details.\ :cite:`fremdling_preparative_2022,esser_mass-selective_2022,esser_cryo-em_2022,esser_cryo-em_2023`

:numref:`fig:setup` shows an overview of the Oxford ESIBD setup,
which combines a commercial mass spectrometer with a custom deposition stage.
Most ESIBD experiments comprise a variety of components including an ion
source, ion guides, mass filters, deflectors, focusing lenses, and
detectors. They require controlling or monitoring DC potentials, RF
amplitudes and frequencies, pressures, temperatures, and ion-beam
currents throughout the experimental setup. While each individual device
is not very complicated, the number of available parameters that have to
be adjusted and documented can quickly result in a massive overhead
where researchers spend more time on documentation than on thinking
about the science, or even the need to repeat experiments due to
incomplete manual documentation. The need for a robust and consistent
interface that allows to perform all elements of the ESIBD workflow with
only a few clicks, while documenting all relevant information
automatically in the background, lead to the creation of the *ESIBD
Explorer*.
