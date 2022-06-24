from fileinput import filename
import os
import shutil
import subprocess
import csv

from rdkit import Chem
from .file_parser import mol2xyz


def cosmo_calc(folder, sdf, cosmotherm_path, cosmo_database_path, charge, mult, T_list, df_pure, done_jobs_record, mol_id, project_dir, task_id):
    basename = os.path.basename(sdf)
    file_name = os.path.splitext(basename)[0]
    parent_dir = os.getcwd()
    
    child_dir = os.path.abspath(os.path.join(folder, file_name))
    os.chdir(child_dir)

    mol = Chem.SDMolSupplier(sdf, removeHs=False, sanitize=False)[0]
    xyz = mol2xyz(mol)

    #create and move to working directory
    os.makedirs("scratch", exist_ok=True)
    os.chdir("scratch")

    if mol_id not in done_jobs_record.COSMO: # not yet done turbomole
        # prepare for turbomole calculation
        os.makedirs("xyz", exist_ok=True)
        xyz_file_name = f'{file_name}.xyz'
        with open(os.path.join("xyz", xyz_file_name), "w+") as f:
            f.write(xyz)

        txtfile = f'{file_name}.txt'
        with open(txtfile, "w+") as f:
            f.write(f"{file_name} {charge} {mult}")

        #run the job
        logfile = file_name + '.log'
        outfile = file_name + '.out'
        with open(outfile, 'w') as out:
            subprocess.run(f'calculate -l {txtfile} -m BP-TZVPD-FINE-COSMO-SP -f xyz -din xyz > {logfile}', shell=True, stdout=out, stderr=out)
            subprocess.run(f'calculate -l {txtfile} -m BP-TZVPD-GAS-SP -f xyz -din xyz > {logfile}', shell=True, stdout=out, stderr=out)

        for file in os.listdir("CosmofilesBP-TZVPD-FINE-COSMO-SP"):
            if file.endswith("cosmo"):
                shutil.copy(os.path.join("CosmofilesBP-TZVPD-FINE-COSMO-SP",file), file)
                shutil.copy(os.path.join("CosmofilesBP-TZVPD-FINE-COSMO-SP",file), os.path.join(child_dir, file))
                break
        else:
            #turbomole calculation failed
            raise
        for file in os.listdir("EnergyfilesBP-TZVPD-FINE-COSMO-SP"):
            if file.endswith("energy"):
                shutil.copy(os.path.join("EnergyfilesBP-TZVPD-FINE-COSMO-SP", file), file)
                shutil.copy(os.path.join("EnergyfilesBP-TZVPD-FINE-COSMO-SP", file), os.path.join(child_dir, file))
                break
        else:
            #turbomole calculation failed
            raise
        done_jobs_record.COSMO[mol_id] = []
        done_jobs_record.save(project_dir, task_id)
    
    # prepare for cosmo calculation
    for index, row in df_pure.iterrows():
        if row.cosmo_name not in done_jobs_record.COSMO.get(mol_id, []):
            script = generate_cosmo_input(file_name, cosmotherm_path, cosmo_database_path, T_list, row)

            inpfile = f'{file_name}_{row.cosmo_name}.inp'
            with open(inpfile, "w+") as f:
                f.write(script)

            cosmo_command = os.path.join(cosmotherm_path, "COSMOtherm", "BIN-LINUX", "cosmotherm")
            outfile = f'{file_name}_{row.cosmo_name}.out'
            tabfile = f'{file_name}_{row.cosmo_name}.tab'
            with open(outfile, 'w') as out:
                subprocess.run(f'{cosmo_command} {inpfile}', shell=True, stdout=out, stderr=out)

            #move files back
            shutil.copy(tabfile, os.path.join(child_dir, tabfile))
            record = done_jobs_record.COSMO.get(mol_id, [])
            record.append(row.cosmo_name)
            done_jobs_record.COSMO[mol_id] = record
            done_jobs_record.save(project_dir, task_id)

    os.chdir(child_dir)

    #remove working directory
    shutil.rmtree("scratch")
    os.remove(sdf)
    os.chdir(parent_dir)
    
def generate_cosmo_input(name, cosmotherm_path, cosmo_database_path, T_list, row):
    """
    Modified from ACS and Yunsie's code
    """

    script = f"""ctd = BP_TZVPD_FINE_21.ctd cdir = "{cosmotherm_path}/COSMOthermX/../COSMOtherm/CTDATA-FILES" ldir = "{cosmotherm_path}/COSMOthermX/../licensefiles"
notempty wtln ehfile
!! generated by COSMOthermX !!
"""

    #solvent
    first_letter = row.cosmo_name[0]
    if not first_letter.isalpha() and not first_letter.isnumeric():
        first_letter = '0'
    if row.source == "COSMOtherm":
        solvent_dir = f"{cosmotherm_path}/COSMOtherm/DATABASE-COSMO/BP-TZVPD-FINE/{first_letter}"
    elif row.source == "COSMObase":
        solvent_dir = f"{cosmo_database_path}/COSMObase2021/BP-TZVPD-FINE/{first_letter}"
    script += "f = \"" + row.cosmo_name + "_c0.cosmo\" fdir=\"" + solvent_dir + "\""
    if int(row.cosmo_conf) > 1:
        script += " Comp = \"" + row.cosmo_name + "\" [ VPfile"
        for k in range(1, int(row.cosmo_conf)):
            script += "\nf = \"" + row.cosmo_name + "_c" + str(k) + ".cosmo\" fdir=\"" + solvent_dir + "\""
        script += " ]\n"
    else:
        script += " VPfile\n"

    #solute
    script += "f = \"" + name + ".cosmo\" fdir=\".\" VPfile\n"
    for T in T_list:
        script += "henry  xh={ 1 0 } tk=" + str(T) + " GSOLV  \n"
    return script

def save_cosmo_results(folder, done_jobs_record, task_id):

    result_file_path = os.path.join(folder, f"cosmo_result_{task_id}")
    header = ['solvent_name', 'solute_name', 'temp (K)',
              'H (bar)', 'ln(gamma)', 'Pvap (bar)', 'Gsolv (kcal/mol)', 'Hsolv (kcal/mol)']
    with open(result_file_path , 'w') as csvfile:
        # creating a csv writer object
        csvwriter = csv.writer(csvfile)
        # writing the header
        csvwriter.writerow(header)

    with open(result_file_path, 'a') as csvfile:
        for mol_id, solvents in done_jobs_record.COSMO.items():
            for solvent in solvents:
                tab_file_path = os.path.join(folder, mol_id, f"{mol_id}_{solvent}.tab")
                each_data_list = read_cosmo_tab_result(tab_file_path)
                each_data_list = get_dHsolv_value(each_data_list)
                csvwriter.writerows(each_data_list)
            
def read_cosmo_tab_result(tab_file_path):
    """
    Modified from Yunsie's code
    """
    each_data_list = []
    # initialize everything
    solvent_name, solute_name, temp = None, None, None
    result_values = None
    with open(tab_file_path, 'r') as f:
        line = f.readline()
        while line:
            # get the temperature and mole fraction
            if "Settings  job" in line:
                temp = line.split('T=')[1].split('K')[0].strip()  # temp in K

            # get the result values
            if "Nr Compound" in line:
                line = f.readline()
                solvent_name = line.split()[1]
                line = f.readline()
                solute_name = line.split()[1]
                result_values = line.split()[2:6]  # H (in bar), ln(gamma), pv (vapor pressure in bar), Gsolv (kcal/mol)
                # save the result as one list
                each_data_list.append(
                    [solvent_name, solute_name, temp] + result_values + [None])
                # initialize everything
                solvent_name, solute_name, temp = None, None, None
                result_values = None
            line = f.readline()
    return each_data_list

def get_dHsolv_value(each_data_list):
    # compute solvation enthalpy
    dGsolv_temp_dict = {}
    ind_298 = None
    for z in range(len(each_data_list)):
        temp = each_data_list[z][5]
        dGsolv = each_data_list[z][9]
        dGsolv_temp_dict[temp] = dGsolv
        if temp == '298.15':
            ind_298 = z
    dGsolv_298 = float(dGsolv_temp_dict['298.15'])
    dSsolv_298 = - (float(dGsolv_temp_dict['299.15']) - float(dGsolv_temp_dict['297.15'])) / (299.15 - 297.15)
    dHsolv_298 = dGsolv_298 + 298.15 * dSsolv_298
    each_data_list[ind_298][10] = '%.8f' % dHsolv_298
    return each_data_list