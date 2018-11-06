# FHIaims.py - IO routines for phonopy-FHI-aims
# methods compatible with the corresponding ones from ase.io.aims
# only minimal subset of functionality required within phonopy context is implemented
#
# Copyright (C) 2009-2011 Joerg Meyer (jm)
# All rights reserved.
#
# This file is part of phonopy.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions
# are met:
#
# * Redistributions of source code must retain the above copyright
#   notice, this list of conditions and the following disclaimer.
#
# * Redistributions in binary form must reproduce the above copyright
#   notice, this list of conditions and the following disclaimer in
#   the documentation and/or other materials provided with the
#   distribution.
#
# * Neither the name of the phonopy project nor the names of its
#   contributors may be used to endorse or promote products derived
#   from this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS
# FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE
# COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT,
# INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,
# BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
# LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN
# ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.

from phonopy.structure.atoms import PhonopyAtoms as Atoms
import numpy

# fidanyan 2018/11/05
# FK 2018/07/19
def lmap(func, lis):
    """Python2/3 compatibility:
        replace map(int, list) with lmap(int, list) that always returns a list
        instead of an iterator. Otherwise conflicts with np.array in python3. """
    return list(map(func, lis))


def read_aims(filename):
    """Method to read FHI-aims geometry files in phonopy context."""

    lines = open(filename, 'r').readlines()

    cell = []
    is_frac = []
    positions = []
    symbols = []
    magmoms = []
    constraints = []
    constrain_warning = True    # prevents errors due to constrained lattice_vectors and some bad-formatting cases
    for line in lines:
        fields = line.split()
        if not len(fields):
            continue
        if fields[0] == "lattice_vector":
            vec = lmap(float, fields[1:4])
            cell.append(vec)
        elif fields[0][0:4] == "atom":
            if fields[0] == "atom":
                frac = False
            elif fields[0] == "atom_frac":
                frac = True
            pos = lmap(float, fields[1:4])
            sym = fields[4]
            is_frac.append(frac)
            positions.append(pos)
            symbols.append(sym)
            magmoms.append(None)
            constraints.append(False)
            constrain_warning = False   # The only correct place for constrain_relaxation is after the atom line

        # implicitly assuming that initial_moments line adhere to FHI-aims geometry.in specification,
        # i.e. two subsequent initial_moments lines do not occur
        # if they do, the value specified in the last line is taken here - without any warning
        elif fields[0] == "initial_moment":
            magmoms[-1] = float(fields[1])

        elif fields[0] == "constrain_relaxation":
            if constrain_warning:
                raise RuntimeError('\'constrain_relaxation\' found in wrong place. '
                                   'If you have constrained lattice vectors, please remove constraints.')
            if fields[1] == ".true.":
                constraints[-1] = True
            constrain_warning = True    # Two 'constrain_relaxation' one after another is bad.

    for (n,frac) in enumerate(is_frac):
        if frac:
            pos = [ sum( [ positions[n][l] * cell[l][i] for l in range(3) ] ) for i in range(3) ]
            positions[n] = pos

    symbols = numpy.asarray(symbols)
    positions = numpy.asarray(positions)
    magmoms = numpy.asarray(magmoms)
    constraints = numpy.asarray(constraints)

    reduced_symbols = symbols[~constraints].tolist()
    reduced_positions = positions[~constraints].tolist()
    reduced_magmoms = magmoms[~constraints].tolist()
    symbols = symbols.tolist()
    positions = positions.tolist()
    magmoms = magmoms.tolist()

    if True in constraints:
        print("geometry.in contains constrained atoms. They will not be included to the Hessian.")

    if None in magmoms:
        atoms = Atoms(cell=cell, symbols=reduced_symbols, positions=reduced_positions)
        all_atoms = Atoms(cell=cell, symbols=symbols, positions=positions)
    else:
        atoms = Atoms(cell=cell, symbols=reduced_symbols, positions=reduced_positions, magmoms=reduced_magmoms)
        all_atoms = Atoms(cell=cell, symbols=symbols, positions=positions, magmoms=magmoms)

    return (atoms, all_atoms, constraints)


def write_aims(filename, atoms, constraints=None):
    """Method to write FHI-aims geometry files in phonopy context."""

    lines = ""
    lines += "# geometry.in for FHI-aims \n"
    lines += "# | generated by phonopy.FHIaims.write_aims() \n"

    lattice_vector_line = "lattice_vector " + "%16.16f "*3 + "\n"
    for vec in atoms.get_cell():
        lines += lattice_vector_line % tuple(vec)

    N = atoms.get_number_of_atoms()

    atom_line = "atom " + "%16.16f "*3 + "%s \n"
    positions = atoms.get_positions()
    symbols = atoms.get_chemical_symbols()

    initial_moment_line = "initial_moment %16.6f\n"
    magmoms = atoms.get_magnetic_moments()

    for n in range(N):
        lines += atom_line % (tuple(positions[n]) + (symbols[n],))
        if magmoms is not None:
            lines += initial_moment_line % magmoms[n]
        if constraints is not None:
            if constraints[n]:
                lines += "constrain_relaxation .true.\n"

    with open(filename, 'w') as f:
        f.write(lines)



class Atoms_with_forces(Atoms):
    """ Hack to phonopy.atoms to maintain ASE compatibility also for forces."""

    def get_forces(self):
        return self.forces


def read_aims_output(filename):
    """ Read FHI-aims output and 
        return geometry, energy and forces from last self-consistency iteration"""

    lines = open(filename, 'r').readlines()

    l = 0
    N = 0
    while l < len(lines):
        line = lines[l]
        if "| Number of atoms" in line:
            N = int(line.split()[5])
        elif "| Unit cell:" in line:
            cell = []
            for i in range(3):
                l += 1
                vec = lmap(float, lines[l].split()[1:4])
                cell.append(vec)
        elif ("Atomic structure:" in line) or ("Updated atomic structure:" in line):
            if "Atomic structure:" in line:
                i_sym = 3
                i_pos_min = 4 ; i_pos_max = 7
            elif "Updated atomic structure:" in line:
                i_sym = 4
                i_pos_min = 1 ; i_pos_max = 4
            l += 1
            symbols = []
            positions = []
            for n in range(N):
               l += 1
               fields = lines[l].split()
               sym = fields[i_sym]
               pos = lmap(float, fields[i_pos_min:i_pos_max])
               symbols.append(sym)
               positions.append(pos)
        elif "Total atomic forces" in line:
            forces = []
            for i in range(N):
                l += 1
                force = lmap(float, lines[l].split()[-3:])
                forces.append(force)
        l += 1
    
    atoms = Atoms_with_forces(cell=cell, symbols=symbols, positions=positions)
    atoms.forces = forces

    return atoms
