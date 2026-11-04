.. image:: https://img.shields.io/badge/license-AGPL--3-blue.png
   :target: https://www.gnu.org/licenses/agpl
   :alt: License: AGPL-3

===========================
Costa Rica location codes
===========================

Costa Rica's territorial division (provinces, cantons, districts and barrios) with the codes of the
Ministerio de Hacienda, and Costa Rican addresses on contacts and companies.

The codes are the ones ``cr_electronic_invoice`` sends in the ``<Ubicacion>`` of electronic invoices.

**Table of contents**

.. contents::
   :local:

Features
========

Location catalogues
~~~~~~~~~~~~~~~~~~~

* 84 cantons, 492 districts and 7,087 barrios with their Hacienda codes, from
  `Codificacionubicacion_V4.4.xlsx <https://www.hacienda.go.cr/docs/Codificacionubicacion_V4.4.xlsx>`_,
  the location table of Hacienda's *Anexos y Estructuras v4.4*. The 7 provinces are Odoo's own, with the
  codes 1 to 7.
* The catalogues are read-only for every user: their data comes from the module.
* Under *Contacts > Configuration > Localization > Cantons / Districts / Neighborhoods*, next to Odoo's
  countries and provinces, with search by name, code and parent, and grouping by parent.

Addresses
~~~~~~~~~

On contacts and companies whose country is Costa Rica:

* Canton, district and barrio, each filtered by the one above. Changing a level clears the levels below it.
* The ZIP is set from the district (province, canton and district codes, e.g. ``10101``) and the city
  from the barrio's name.
* Province, canton and district share a line, then the barrio and the ZIP.
* *Street* is shown as "Directions..." ("Otras señas..."), *State* as "Province" ("Provincia"), and
  *Street 2* and *City* are hidden.

Other countries keep Odoo's address form.

Address format
~~~~~~~~~~~~~~

Costa Rican addresses are printed in the order Correos de Costa Rica gives the Universal Postal Union
(`UPU addressing sheet for Costa Rica <https://www.upu.int/UPU/media/upu/PostalEntitiesFiles/addressingUnit/criEn.pdf>`_),
with the barrio after the district, as in Hacienda's ``<Ubicacion>``::

    200 metros al este de la Iglesia de Fátima, 50 metros al norte   (otras señas)
    San José, Montes de Oca, San Pedro, Yoses                        (province, canton, district, barrio)
    11501
    Costa Rica

The tax ID label of Costa Rica is "Identificación".

Known issues
============

* The order of the address fields on the form follows the company's country, as in standard Odoo, so
  Costa Rican addresses may look different under companies of some other countries. It only affects how
  the form looks: the address data, the printed address and electronic invoices are not affected.
* Contacts of a company don't inherit its canton, district and barrio yet.
* Odoo 20 dropped the fallback of the ``placeholder_field`` option to the static placeholder
  (`odoo/odoo#300493 <https://github.com/odoo/odoo/issues/300493>`_), so the module provides Odoo's
  "Street..." and "State" for other countries until it is fixed.

Credits
=======

Authors
~~~~~~~

* Delfix S.A.

  * Mario Arias <the.clone.master@gmail.com>

* Charlie Monge <charlit02390@gmail.com>

* `TechMicro Inc S.A. <https://www.techmicrocr.com>`_

  * Jason Ulloa <jason.ulloa@techmicrocr.com>

* `AKUREY S.A. <https://www.akurey.com>`_

  * Carlos Wong <cwong@akurey.com>
  * Sergio Hidalgo <shidalgo@akurey.com>
  * Joaquin Mena <jmena@akurey.com>
  * Julio Barboza <jbarboza@akurey.com>

Contributors
~~~~~~~~~~~~

* Nehemias Herrera
* Esteban Monge <estebanmonge@riseup.net>
