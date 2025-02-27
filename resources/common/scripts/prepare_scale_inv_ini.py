#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Copyright IBM Corporation 2018

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.

You may obtain a copy of the License at
http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

import argparse
import configparser
import json
import pathlib
import os
import re
import sys
import yaml


def cleanup(target_file):
    """ Cleanup host inventory, group_vars """
    if os.path.exists(target_file):
        os.remove(target_file)


def calculate_pagepool(memory_size, max_pagepool_gb):
    """ Calculate pagepool """
    # 1 MiB = 1.048576 MB
    mem_size_mb = int(int(memory_size) * 1.048576)
    # 1 MB = 0.001 GB
    mem_size_gb = int(mem_size_mb * 0.001)
    pagepool_gb = max(int(int(mem_size_gb)*int(25)*0.01), 1)
    if pagepool_gb > int(max_pagepool_gb):
        pagepool = int(max_pagepool_gb)
    else:
        pagepool = pagepool_gb
    return "{}G".format(pagepool)


def create_directory(target_directory):
    """ Create specified directory """
    pathlib.Path(target_directory).mkdir(parents=True, exist_ok=True)


def read_json_file(json_path):
    """ Read inventory as json file """
    tf_inv = {}
    try:
        with open(json_path) as json_handler:
            try:
                tf_inv = json.load(json_handler)
            except json.decoder.JSONDecodeError:
                print("Provided terraform inventory file (%s) is not a valid "
                      "json." % json_path)
                sys.exit(1)
    except OSError:
        print("Provided terraform inventory file (%s) does not exist." % json_path)
        sys.exit(1)

    return tf_inv


def write_json_file(json_data, json_path):
    """ Write inventory to json file """
    with open(json_path, 'w') as json_handler:
        json.dump(json_data, json_handler, indent=4)


def write_to_file(filepath, filecontent):
    """ Write to specified file """
    with open(filepath, "w") as file_handler:
        file_handler.write(filecontent)


def prepare_ansible_playbook(hosts_config, cluster_config, cluster_key_file):
    """ Write to playbook """
    content = """---
# Ensure provisioned VMs are up and Passwordless SSH setup
# has been compleated and operational
- name: Check passwordless SSH connection is setup
  hosts: {hosts_config}
  any_errors_fatal: true
  gather_facts: false
  connection: local
  tasks:
  - name: Check passwordless SSH on all scale inventory hosts
    shell: ssh {{{{ ansible_ssh_common_args }}}} -i {cluster_key_file} root@{{{{ inventory_hostname }}}} "echo PASSWDLESS_SSH_ENABLED"
    register: result
    until: result.stdout.find("PASSWDLESS_SSH_ENABLED") != -1
    retries: 60
    delay: 10
# Validate Scale packages existence to skip node role
- name: Check if Scale packages already installed on node
  hosts: scale_nodes
  gather_facts: false
  vars:
    scale_packages_installed: true
    scale_packages:
      - gpfs.base
      - gpfs.adv
      - gpfs.crypto
      - gpfs.docs
      - gpfs.gpl
      - gpfs.gskit
      - gpfs.gss.pmcollector
      - gpfs.gss.pmsensors
      - gpfs.gui
      - gpfs.java
  tasks:
  - name: Check if scale packages are already installed
    shell: rpm -q "{{{{ item }}}}"
    loop: "{{{{ scale_packages }}}}"
    register: scale_packages_check
    ignore_errors: true

  - name: Set scale packages installation variable
    set_fact:
      scale_packages_installed: false
    when:  item.rc != 0
    loop: "{{{{ scale_packages_check.results }}}}"
    ignore_errors: true

# Install and config Spectrum Scale on nodes
- hosts: {hosts_config}
  any_errors_fatal: true
  pre_tasks:
     - include_vars: group_vars/{cluster_config}
  roles:
     - core_prepare
     - {{ role: core_install, when: "scale_packages_installed is false" }}
     - core_configure
     - gui_prepare
     - {{ role: gui_install, when: "scale_packages_installed is false" }}
     - gui_configure
     - gui_verify
     - perfmon_prepare
     - {{ role: perfmon_install, when: "scale_packages_installed is false" }}
     - perfmon_configure
     - perfmon_verify
""".format(hosts_config=hosts_config, cluster_config=cluster_config,
           cluster_key_file=cluster_key_file)
    return content


def prepare_packer_ansible_playbook(hosts_config, cluster_config):
    """ Write to playbook """
    content = """---
# Install and config Spectrum Scale on nodes
- hosts: {hosts_config}
  any_errors_fatal: true
  pre_tasks:
     - include_vars: group_vars/{cluster_config}
  roles:
     - core_configure
     - gui_configure
     - gui_verify
     - perfmon_configure
     - perfmon_verify
""".format(hosts_config=hosts_config, cluster_config=cluster_config)
    return content


def prepare_nogui_ansible_playbook(hosts_config, cluster_config):
    """ Write to playbook """
    content = """---
# Install and config Spectrum Scale on nodes
- hosts: {hosts_config}
  any_errors_fatal: true
  pre_tasks:
     - include_vars: group_vars/{cluster_config}
  roles:
     - core_prepare
     - core_install
     - core_configure
""".format(hosts_config=hosts_config, cluster_config=cluster_config)
    return content


def prepare_nogui_packer_ansible_playbook(hosts_config, cluster_config):
    """ Write to playbook """
    content = """---
# Install and config Spectrum Scale on nodes
- hosts: {hosts_config}
  any_errors_fatal: true
  pre_tasks:
     - include_vars: group_vars/{cluster_config}
  roles:
     - core_configure
""".format(hosts_config=hosts_config, cluster_config=cluster_config)
    return content


  def initialize_cluster_details(scale_version, cluster_name, username,
                               password, scale_profile_path,
                               scale_replica_config):
    """ Initialize cluster details.
    :args: scale_version (string), cluster_name (string),
           username (string), password (string), scale_profile_path (string),
           scale_replica_config (bool)
    """
    cluster_details = {}
    cluster_details['scale_version'] = scale_version
    cluster_details['scale_cluster_clustername'] = cluster_name
    cluster_details['scale_service_gui_start'] = "True"
    cluster_details['scale_gui_admin_user'] = username
    cluster_details['scale_gui_admin_password'] = password
    cluster_details['scale_gui_admin_role'] = "Administrator"
    cluster_details['scale_sync_replication_config'] = scale_replica_config
    cluster_details['scale_cluster_profile_name'] = str(
        pathlib.PurePath(scale_profile_path).stem)
    cluster_details['scale_cluster_profile_dir_path'] = str(
        pathlib.PurePath(scale_profile_path).parent)
    return cluster_details


def get_host_format(node):
    """ Return host entries """
    host_format = f"{node['ip_addr']} scale_cluster_quorum={node['is_quorum']} scale_cluster_manager={node['is_manager']} scale_cluster_gui={node['is_gui']} scale_zimon_collector={node['is_collector']} is_nsd_server={node['is_nsd']} is_admin_node={node['is_admin']} ansible_user={node['user']} ansible_ssh_private_key_file={node['key_file']} ansible_python_interpreter=/usr/bin/python3 scale_nodeclass={node['class']}"
    return host_format


def initialize_node_details(az_count, cls_type, compute_private_ips,
                            storage_private_ips, desc_private_ips, quorum_count,
                            user, key_file):
    """ Initialize node details for cluster definition.
    :args: az_count (int), cls_type (string), compute_private_ips (list),
           storage_private_ips (list), desc_private_ips (list),
           quorum_count (int), user (string), key_file (string)
    """
    node_details, node = [], {}
    if cls_type == 'compute':
        start_quorum_assign = quorum_count - 1
        for each_ip in compute_private_ips:
            if compute_private_ips.index(each_ip) <= (start_quorum_assign) and \
                    compute_private_ips.index(each_ip) <= (manager_count - 1):
                if compute_private_ips.index(each_ip) == 0:
                    node = {'ip_addr': each_ip, 'is_quorum': True, 'is_manager': True,
                            'is_gui': True, 'is_collector': True, 'is_nsd': False,
                            'is_admin': True, 'user': user, 'key_file': key_file,
                            'class': "computenodegrp"}
                    write_json_file({'compute_cluster_gui_ip_address': each_ip},
                                    "%s/%s" % (str(pathlib.PurePath(ARGUMENTS.tf_inv_path).parent),
                                               "compute_cluster_gui_details.json"))
                elif compute_private_ips.index(each_ip) == 1:
                    node = {'ip_addr': each_ip, 'is_quorum': True, 'is_manager': True,
                            'is_gui': False, 'is_collector': True, 'is_nsd': False,
                            'is_admin': False, 'user': user, 'key_file': key_file,
                            'class': "computenodegrp"}
                else:
                    node = {'ip_addr': each_ip, 'is_quorum': True, 'is_manager': True,
                            'is_gui': False, 'is_collector': False, 'is_nsd': False,
                            'is_admin': False, 'user': user, 'key_file': key_file,
                            'class': "computenodegrp"}
            elif compute_private_ips.index(each_ip) <= (start_quorum_assign) and \
                    compute_private_ips.index(each_ip) > (manager_count - 1):
                node = {'ip_addr': each_ip, 'is_quorum': True, 'is_manager': False,
                        'is_gui': False, 'is_collector': False, 'is_nsd': False,
                        'is_admin': False, 'user': user, 'key_file': key_file,
                        'class': "computenodegrp"}
            else:
                node = {'ip_addr': each_ip, 'is_quorum': False, 'is_manager': False,
                        'is_gui': False, 'is_collector': False, 'is_nsd': False,
                        'is_admin': False, 'user': user, 'key_file': key_file,
                        'class': "computenodegrp"}
            node_details.append(get_host_format(node))
    elif cls_type == 'storage' and az_count == 1:
        start_quorum_assign = quorum_count - 1
        for each_ip in storage_private_ips:
            if storage_private_ips.index(each_ip) <= (start_quorum_assign) and \
                    storage_private_ips.index(each_ip) <= (manager_count - 1):
                if storage_private_ips.index(each_ip) == 0:
                    node = {'ip_addr': each_ip, 'is_quorum': True, 'is_manager': True,
                            'is_gui': True, 'is_collector': True, 'is_nsd': True,
                            'is_admin': True, 'user': user, 'key_file': key_file,
                            'class': "storagenodegrp"}
                    write_json_file({'storage_cluster_gui_ip_address': each_ip},
                                    "%s/%s" % (str(pathlib.PurePath(ARGUMENTS.tf_inv_path).parent),
                                               "storage_cluster_gui_details.json"))
                elif storage_private_ips.index(each_ip) == 1:
                    node = {'ip_addr': each_ip, 'is_quorum': True, 'is_manager': True,
                            'is_gui': False, 'is_collector': True, 'is_nsd': True,
                            'is_admin': False, 'user': user, 'key_file': key_file,
                            'class': "storagenodegrp"}
                else:
                    node = {'ip_addr': each_ip, 'is_quorum': True, 'is_manager': False,
                            'is_gui': False, 'is_collector': True, 'is_nsd': True,
                            'is_admin': False, 'user': user, 'key_file': key_file,
                            'class': "storagenodegrp"}
            elif storage_private_ips.index(each_ip) <= (start_quorum_assign) and \
                    storage_private_ips.index(each_ip) > (manager_count - 1):
                node = {'ip_addr': each_ip, 'is_quorum': True, 'is_manager': False,
                        'is_gui': False, 'is_collector': False, 'is_nsd': True,
                        'is_admin': False, 'user': user, 'key_file': key_file,
                        'class': "storagenodegrp"}
            else:
                node = {'ip_addr': each_ip, 'is_quorum': False, 'is_manager': False,
                        'is_gui': False, 'is_collector': False, 'is_nsd': True,
                        'is_admin': False, 'user': user, 'key_file': key_file,
                        'class': "storagenodegrp"}
            node_details.append(get_host_format(node))
    elif cls_type == 'storage' and az_count > 1:
        for each_ip in desc_private_ips:
            node = {'ip_addr': each_ip, 'is_quorum': True, 'is_manager': False,
                    'is_gui': False, 'is_collector': False, 'is_nsd': True,
                    'is_admin': False, 'user': user, 'key_file': key_file,
                    'class': "computedescnodegrp"}
            node_details.append(get_host_format(node))

        if az_count > 1:
            # Storage/NSD nodes to be quorum nodes (quorum_count - 2 as index starts from 0)
            start_quorum_assign = quorum_count - 2
        else:
            # Storage/NSD nodes to be quorum nodes (quorum_count - 1 as index starts from 0)
            start_quorum_assign = quorum_count - 1

        for each_ip in storage_private_ips:
            if storage_private_ips.index(each_ip) <= (start_quorum_assign) and \
                    storage_private_ips.index(each_ip) <= (manager_count - 1):
                if storage_private_ips.index(each_ip) == 0:
                    node = {'ip_addr': each_ip, 'is_quorum': True, 'is_manager': True,
                            'is_gui': True, 'is_collector': True, 'is_nsd': True,
                            'is_admin': True, 'user': user, 'key_file': key_file,
                            'class': "storagenodegrp"}
                    write_json_file({'storage_cluster_gui_ip_address': each_ip},
                                    "%s/%s" % (str(pathlib.PurePath(ARGUMENTS.tf_inv_path).parent),
                                               "storage_cluster_gui_details.json"))
                elif storage_private_ips.index(each_ip) == 1:
                    node = {'ip_addr': each_ip, 'is_quorum': True, 'is_manager': True,
                            'is_gui': False, 'is_collector': True, 'is_nsd': True,
                            'is_admin': True, 'user': user, 'key_file': key_file,
                            'class': "storagenodegrp"}
                else:
                    node = {'ip_addr': each_ip, 'is_quorum': True, 'is_manager': True,
                            'is_gui': False, 'is_collector': False, 'is_nsd': True,
                            'is_admin': True, 'user': user, 'key_file': key_file,
                            'class': "storagenodegrp"}
            elif storage_private_ips.index(each_ip) <= (start_quorum_assign) and \
                    storage_private_ips.index(each_ip) > (manager_count - 1):
                node = {'ip_addr': each_ip, 'is_quorum': True, 'is_manager': False,
                        'is_gui': False, 'is_collector': False, 'is_nsd': True,
                        'is_admin': True, 'user': user, 'key_file': key_file,
                        'class': "storagenodegrp"}
            else:
                node = {'ip_addr': each_ip, 'is_quorum': False, 'is_manager': False,
                        'is_gui': False, 'is_collector': False, 'is_nsd': True,
                        'is_admin': False, 'user': user, 'key_file': key_file,
                        'class': "storagenodegrp"}
            node_details.append(get_host_format(node))
    elif cls_type == 'combined':
        for each_ip in desc_private_ips:
            node = {'ip_addr': each_ip, 'is_quorum': True, 'is_manager': False,
                    'is_gui': False, 'is_collector': False, 'is_nsd': True,
                    'is_admin': False, 'user': user, 'key_file': key_file,
                    'class': "computedescnodegrp"}
            node_details.append(get_host_format(node))

        if az_count > 1:
            # Storage/NSD nodes to be quorum nodes (quorum_count - 2 as index starts from 0)
            start_quorum_assign = quorum_count - 2
        else:
            # Storage/NSD nodes to be quorum nodes (quorum_count - 1 as index starts from 0)
            start_quorum_assign = quorum_count - 1

        for each_ip in storage_private_ips:
            if storage_private_ips.index(each_ip) <= (start_quorum_assign) and \
                    storage_private_ips.index(each_ip) <= (manager_count - 1):
                if storage_private_ips.index(each_ip) == 0:
                    node = {'ip_addr': each_ip, 'is_quorum': True, 'is_manager': True,
                            'is_gui': True, 'is_collector': True, 'is_nsd': True,
                            'is_admin': True, 'user': user, 'key_file': key_file,
                            'class': "storagenodegrp"}
                elif storage_private_ips.index(each_ip) == 1:
                    node = {'ip_addr': each_ip, 'is_quorum': True, 'is_manager': True,
                            'is_gui': False, 'is_collector': True, 'is_nsd': True,
                            'is_admin': True, 'user': user, 'key_file': key_file,
                            'class': "storagenodegrp"}
                else:
                    node = {'ip_addr': each_ip, 'is_quorum': True, 'is_manager': True,
                            'is_gui': False, 'is_collector': False, 'is_nsd': True,
                            'is_admin': True, 'user': user, 'key_file': key_file,
                            'class': "storagenodegrp"}
            elif storage_private_ips.index(each_ip) <= (start_quorum_assign) and \
                    storage_private_ips.index(each_ip) > (manager_count - 1):
                node = {'ip_addr': each_ip, 'is_quorum': True, 'is_manager': False,
                        'is_gui': False, 'is_collector': False, 'is_nsd': True,
                        'is_admin': True, 'user': user, 'key_file': key_file,
                        'class': "storagenodegrp"}
            else:
                node = {'ip_addr': each_ip, 'is_quorum': False, 'is_manager': False,
                        'is_gui': False, 'is_collector': False, 'is_nsd': True,
                        'is_admin': False, 'user': user, 'key_file': key_file,
                        'class': "storagenodegrp"}
            node_details.append(get_host_format(node))

        if az_count > 1:
            if len(storage_private_ips) - len(desc_private_ips) >= quorum_count:
                quorums_left = 0
            else:
                quorums_left = quorum_count - \
                    len(storage_private_ips) - len(desc_private_ips)
        else:
            if len(storage_private_ips) > quorum_count:
                quorums_left = 0
            else:
                quorums_left = quorum_count - len(storage_private_ips)

        # Additional quorums assign to compute nodes
        if quorums_left > 0:
            for each_ip in compute_private_ips[0:quorums_left]:
                node = {'ip_addr': each_ip, 'is_quorum': True, 'is_manager': False,
                        'is_gui': False, 'is_collector': False, 'is_nsd': False,
                        'is_admin': True, 'user': user, 'key_file': key_file,
                        'class': "computenodegrp"}
                node_details.append(get_host_format(node))
            for each_ip in compute_private_ips[quorums_left:]:
                node = {'ip_addr': each_ip, 'is_quorum': False, 'is_manager': False,
                        'is_gui': False, 'is_collector': False, 'is_nsd': False,
                        'is_admin': False, 'user': user, 'key_file': key_file,
                        'class': "computenodegrp"}
                node_details.append(get_host_format(node))

        if quorums_left == 0:
            for each_ip in compute_private_ips:
                node = {'ip_addr': each_ip, 'is_quorum': False, 'is_manager': False,
                        'is_gui': False, 'is_collector': False, 'is_nsd': False,
                        'is_admin': False, 'user': user, 'key_file': key_file,
                        'class': "computenodegrp"}
                node_details.append(get_host_format(node))

    return node_details


def initialize_scale_config_details(node_classes, param_key, param_value):
    """ Initialize scale cluster config details.
    :args: node_class (list), param_key (string), param_value (string)
    """
    scale_config = {}
    scale_config['scale_config'], scale_config['scale_cluster_config'] = [], {}
    for each_node in node_classes:
        scale_config['scale_config'].append({"nodeclass": each_node,
                                             "params": [{param_key: param_value}]})
    scale_config['scale_cluster_config']['ephemeral_port_range'] = "60000-61000"
    return scale_config


def get_disks_list(az_count, disk_mapping, desc_disk_mapping):
    """ Initialize disk list. """
    disks_list = []

    # Map storage nodes to failure groups based on AZ and subnet variations
    failure_group1, failure_group2 = [], []
    if az_count == 1:
        # Single AZ, just split list equally
        num_storage_nodes = len(list(disk_mapping))
        mid_index = num_storage_nodes//2
        failure_group1 = list(disk_mapping)[:mid_index]
        failure_group2 = list(disk_mapping)[mid_index:]
    else:
        # Multi AZ, split based on subnet match
        subnet_pattern = re.compile(r'\d{1,3}\.\d{1,3}\.(\d{1,3})\.\d{1,3}')
        subnet1A = subnet_pattern.findall(list(disk_mapping)[0])
        for each_ip in disk_mapping:
            current_subnet = subnet_pattern.findall(each_ip)
            if current_subnet[0] == subnet1A[0]:
                failure_group1.append(each_ip)
            else:
                failure_group2.append(each_ip)

    storage_instances = []
    max_len = max(len(failure_group1), len(failure_group2))
    idx = 0
    while idx < max_len:
        if idx < len(failure_group1):
            storage_instances.append(failure_group1[idx])

        if idx < len(failure_group2):
            storage_instances.append(failure_group2[idx])

        idx = idx + 1

    for each_ip, disk_per_ip in disk_mapping.items():
        if each_ip in failure_group1:
            for each_disk in disk_per_ip:
                disks_list.append({"device": each_disk,
                                   "failureGroup": 1, "servers": each_ip,
                                   "usage": "dataAndMetadata", "pool": "system"})
        if each_ip in failure_group2:
            for each_disk in disk_per_ip:
                disks_list.append({"device": each_disk,
                                   "failureGroup": 2, "servers": each_ip,
                                   "usage": "dataAndMetadata", "pool": "system"})

    # Append "descOnly" disk details
    if len(desc_disk_mapping.keys()):
        disks_list.append({"device": list(desc_disk_mapping.values())[0][0],
                           "failureGroup": 3,
                           "servers": list(desc_disk_mapping.keys())[0],
                           "usage": "descOnly", "pool": "system"})
    return disks_list


def initialize_scale_storage_details(az_count, fs_mount, block_size, disk_details):
    """ Initialize storage details.
    :args: az_count (int), fs_mount (string), block_size (string),
           disks_list (list)
    """
    storage = {}
    storage['scale_storage'] = []
    if az_count > 1:
        data_replicas = 2
        metadata_replicas = 2
    else:
        data_replicas = 1
        metadata_replicas = 2

    storage['scale_storage'].append({"filesystem": pathlib.PurePath(fs_mount).name,
                                     "blockSize": block_size,
                                     "defaultDataReplicas": data_replicas,
                                     "defaultMetadataReplicas": metadata_replicas,
                                     "automaticMountOption": "true",
                                     "defaultMountPoint": fs_mount,
                                     "disks": disk_details})
    return storage


if __name__ == "__main__":
    PARSER = argparse.ArgumentParser(description='Convert terraform inventory '
                                                 'to ansible inventory format '
                                                 'install and configuration.')
    PARSER.add_argument('--tf_inv_path', required=True,
                        help='Terraform inventory file path')
    PARSER.add_argument('--install_infra_path', required=True,
                        help='Spectrum Scale install infra clone parent path')
    PARSER.add_argument('--instance_private_key', required=True,
                        help='Spectrum Scale instances SSH private key path')
    PARSER.add_argument('--bastion_user',
                        help='Bastion OS Login username')
    PARSER.add_argument('--bastion_ip',
                        help='Bastion SSH public ip address')
    PARSER.add_argument('--bastion_ssh_private_key',
                        help='Bastion SSH private key path')
    PARSER.add_argument('--memory_size', help='Instance memory size')
    PARSER.add_argument('--max_pagepool_gb', help='maximum pagepool size in GB',
                        default=1)
    PARSER.add_argument('--using_packer_image', help='skips gpfs rpm copy')
    PARSER.add_argument('--using_rest_initialization',
                        help='skips gui configuration')
    PARSER.add_argument('--gui_username', required=True,
                        help='Spectrum Scale GUI username')
    PARSER.add_argument('--gui_password', required=True,
                        help='Spectrum Scale GUI password')
    PARSER.add_argument('--verbose', action='store_true',
                        help='print log messages')

    ARGUMENTS = PARSER.parse_args()

    cluster_type, gui_username, gui_password = None, None, None
    profile_path, replica_config, scale_config = None, None, {}
    # Step-1: Read the inventory file
    TF = read_json_file(ARGUMENTS.tf_inv_path)
    if ARGUMENTS.verbose:
        print("Parsed terraform output: %s" % json.dumps(TF, indent=4))

    # Step-2: Identify the cluster type
    if len(TF['storage_cluster_instance_private_ips']) == 0 and \
            len(TF['compute_cluster_instance_private_ips']) > 0:
        cluster_type = "compute"
        cleanup("%s/%s/%s_inventory.ini" % (ARGUMENTS.install_infra_path,
                                            "ibm-spectrum-scale-install-infra",
                                            cluster_type))
        cleanup("%s/%s_cluster_gui_details.json" % (str(pathlib.PurePath(ARGUMENTS.tf_inv_path).parent),
                                                    cluster_type))
        cleanup("/%s/%s/%s_cloud_playbook.yaml" % (ARGUMENTS.install_infra_path,
                                                   "ibm-spectrum-scale-install-infra",
                                                   cluster_type))
        cleanup("%s/%s/%s/%s" % (ARGUMENTS.install_infra_path,
                                 "ibm-spectrum-scale-install-infra",
                                 "group_vars", "%s_cluster_config.yaml" % cluster_type))
        gui_username = ARGUMENTS.gui_username
        gui_password = ARGUMENTS.gui_password
        profile_path = "%s/computesncparams" % ARGUMENTS.install_infra_path
        replica_config = False
        pagepool_size = calculate_pagepool(
            ARGUMENTS.memory_size, ARGUMENTS.max_pagepool_gb)
        scale_config = initialize_scale_config_details(
            ["computenodegrp"], "pagepool", pagepool_size)
    elif len(TF['compute_cluster_instance_private_ips']) == 0 and \
            len(TF['storage_cluster_instance_private_ips']) > 0 and \
            len(TF['vpc_availability_zones']) == 1:
        # single az storage cluster
        cluster_type = "storage"
        cleanup("%s/%s/%s_inventory.ini" % (ARGUMENTS.install_infra_path,
                                            "ibm-spectrum-scale-install-infra",
                                            cluster_type))
        cleanup("%s/%s_cluster_gui_details.json" % (str(pathlib.PurePath(ARGUMENTS.tf_inv_path).parent),
                                                    cluster_type))
        cleanup("/%s/%s/%s_cloud_playbook.yaml" % (ARGUMENTS.install_infra_path,
                                                   "ibm-spectrum-scale-install-infra",
                                                   cluster_type))
        cleanup("%s/%s/%s/%s" % (ARGUMENTS.install_infra_path,
                                 "ibm-spectrum-scale-install-infra",
                                 "group_vars", "%s_cluster_config.yaml" % cluster_type))
        gui_username = ARGUMENTS.gui_username
        gui_password = ARGUMENTS.gui_password
        profile_path = "%s/storagesncparams" % ARGUMENTS.install_infra_path
        replica_config = bool(len(TF['vpc_availability_zones']) > 1)
        pagepool_size = calculate_pagepool(
            ARGUMENTS.memory_size, ARGUMENTS.max_pagepool_gb)
        scale_config = initialize_scale_config_details(
            ["storagenodegrp"], "pagepool", pagepool_size)
    elif len(TF['compute_cluster_instance_private_ips']) == 0 and \
            len(TF['storage_cluster_instance_private_ips']) > 0 and \
            len(TF['vpc_availability_zones']) > 1 and \
            len(TF['storage_cluster_desc_instance_private_ips']) > 0:
        # multi az storage cluster
        cluster_type = "storage"
        cleanup("%s/%s/%s_inventory.ini" % (ARGUMENTS.install_infra_path,
                                            "ibm-spectrum-scale-install-infra",
                                            cluster_type))
        cleanup("%s/%s_cluster_gui_details.json" % (str(pathlib.PurePath(ARGUMENTS.tf_inv_path).parent),
                                                    cluster_type))
        cleanup("/%s/%s/%s_cloud_playbook.yaml" % (ARGUMENTS.install_infra_path,
                                                   "ibm-spectrum-scale-install-infra",
                                                   cluster_type))
        cleanup("%s/%s/%s/%s" % (ARGUMENTS.install_infra_path,
                                 "ibm-spectrum-scale-install-infra",
                                 "group_vars", "%s_cluster_config.yaml" % cluster_type))
        gui_username = ARGUMENTS.gui_username
        gui_password = ARGUMENTS.gui_password
        profile_path = "%s/storagesncparams" % ARGUMENTS.install_infra_path
        replica_config = bool(len(TF['vpc_availability_zones']) > 1)
        pagepool_size = calculate_pagepool(
            ARGUMENTS.memory_size, ARGUMENTS.max_pagepool_gb)
        scale_config = initialize_scale_config_details(
            ["storagenodegrp", "computedescnodegrp"], "pagepool", pagepool_size)
    else:
        cluster_type = "combined"
        cleanup("%s/%s/%s_inventory.ini" % (ARGUMENTS.install_infra_path,
                                            "ibm-spectrum-scale-install-infra",
                                            cluster_type))
        cleanup("/%s/%s/%s_cloud_playbook.yaml" % (ARGUMENTS.install_infra_path,
                                                   "ibm-spectrum-scale-install-infra",
                                                   cluster_type))
        cleanup("%s/%s/%s/%s" % (ARGUMENTS.install_infra_path,
                                 "ibm-spectrum-scale-install-infra",
                                 "group_vars", "%s_cluster_config.yaml" % cluster_type))
        gui_username = ARGUMENTS.gui_username
        gui_password = ARGUMENTS.gui_password
        profile_path = "%s/scalesncparams" % ARGUMENTS.install_infra_path
        replica_config = bool(len(TF['vpc_availability_zones']) > 1)
        pagepool_size = calculate_pagepool(
            ARGUMENTS.memory_size, ARGUMENTS.max_pagepool_gb)
        if len(TF['vpc_availability_zones']) == 1:
            scale_config = initialize_scale_config_details(
                ["storagenodegrp", "computenodegrp"], "pagepool", pagepool_size)
        else:
            scale_config = initialize_scale_config_details(
                ["storagenodegrp", "computenodegrp", "computedescnodegrp"], "pagepool", pagepool_size)

    print("Identified cluster type: %s" % cluster_type)

    # Step-3: Identify if tie breaker needs to be counted for storage
    if len(TF['vpc_availability_zones']) > 1:
        total_node_count = len(TF['compute_cluster_instance_private_ips']) + \
            len(TF['storage_cluster_desc_instance_private_ips']) + \
            len(TF['storage_cluster_instance_private_ips'])
    else:
        total_node_count = len(TF['compute_cluster_instance_private_ips']) + \
            len(TF['storage_cluster_instance_private_ips'])

    if ARGUMENTS.verbose:
        print("Total node count: ", total_node_count)

    # Determine total number of quorum, manager nodes to be in the cluster
    # manager designates the node as part of the pool of nodes from which
    # file system managers and token managers are selected.
    quorum_count, manager_count = 0, 2
    if total_node_count < 4:
        quorum_count = total_node_count
    elif 4 <= total_node_count < 10:
        quorum_count = 3
    elif 10 <= total_node_count < 19:
        quorum_count = 5
    else:
        quorum_count = 7

    if ARGUMENTS.verbose:
        print("Total quorum count: ", quorum_count)

    # Step-4: Create playbook
    if ARGUMENTS.using_packer_image == "false" and ARGUMENTS.using_rest_initialization == "true":
        playbook_content = prepare_ansible_playbook(
            "scale_nodes", "%s_cluster_config.yaml" % cluster_type,
            ARGUMENTS.instance_private_key)
        write_to_file("/%s/%s/%s_cloud_playbook.yaml" % (ARGUMENTS.install_infra_path,
                                                         "ibm-spectrum-scale-install-infra",
                                                         cluster_type), playbook_content)
    elif ARGUMENTS.using_packer_image == "true" and ARGUMENTS.using_rest_initialization == "true":
        playbook_content = prepare_packer_ansible_playbook(
            "scale_nodes", "%s_cluster_config.yaml" % cluster_type)
        write_to_file("/%s/%s/%s_cloud_playbook.yaml" % (ARGUMENTS.install_infra_path,
                                                         "ibm-spectrum-scale-install-infra",
                                                         cluster_type), playbook_content)
    elif ARGUMENTS.using_packer_image == "false" and ARGUMENTS.using_rest_initialization == "false":
        playbook_content = prepare_nogui_ansible_playbook(
            "scale_nodes", "%s_cluster_config.yaml" % cluster_type)
        write_to_file("/%s/%s/%s_cloud_playbook.yaml" % (ARGUMENTS.install_infra_path,
                                                         "ibm-spectrum-scale-install-infra",
                                                         cluster_type), playbook_content)
    elif ARGUMENTS.using_packer_image == "true" and ARGUMENTS.using_rest_initialization == "false":
        playbook_content = prepare_nogui_packer_ansible_playbook(
            "scale_nodes", "%s_cluster_config.yaml" % cluster_type)
        write_to_file("/%s/%s/%s_cloud_playbook.yaml" % (ARGUMENTS.install_infra_path,
                                                         "ibm-spectrum-scale-install-infra",
                                                         cluster_type), playbook_content)
    if ARGUMENTS.verbose:
        print("Content of ansible playbook:\n", playbook_content)

    # Step-5: Create hosts
    config = configparser.ConfigParser(allow_no_value=True)
    node_details = initialize_node_details(len(TF['vpc_availability_zones']), cluster_type,
                                           TF['compute_cluster_instance_private_ips'],
                                           TF['storage_cluster_instance_private_ips'],
                                           TF['storage_cluster_desc_instance_private_ips'],
                                           quorum_count, "root", ARGUMENTS.instance_private_key)
    node_template = ""
    for each_entry in node_details:
        if ARGUMENTS.bastion_ssh_private_key is None:
            each_entry = each_entry + " " + "ansible_ssh_common_args="""
            node_template = node_template + each_entry + "\n"
        else:
            proxy_command = f"ssh -p 22 -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -W %h:%p {ARGUMENTS.bastion_user}@{ARGUMENTS.bastion_ip} -i {ARGUMENTS.bastion_ssh_private_key}"
            each_entry = each_entry + " " + \
                "ansible_ssh_common_args='-o ControlMaster=auto -o ControlPersist=30m -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no -o ProxyCommand=\"" + proxy_command + "\"'"
            node_template = node_template + each_entry + "\n"

    if TF['resource_prefix']:
        cluster_name = TF['resource_prefix']
    else:
        cluster_name = "%s.%s" % ("spectrum-scale", cluster_type)

    config['all:vars'] = initialize_cluster_details(TF['scale_version'],
                                                    cluster_name,
                                                    gui_username,
                                                    gui_password,
                                                    profile_path,
                                                    replica_config)
    with open("%s/%s/%s_inventory.ini" % (ARGUMENTS.install_infra_path,
                                          "ibm-spectrum-scale-install-infra",
                                          cluster_type), 'w') as configfile:
        configfile.write('[scale_nodes]' + "\n")
        configfile.write(node_template)
        config.write(configfile)

    if ARGUMENTS.verbose:
        config.read("%s/%s/%s_inventory.ini" % (ARGUMENTS.install_infra_path,
                                                "ibm-spectrum-scale-install-infra",
                                                cluster_type))
        print("Content of %s/%s/%s_inventory.ini" % (ARGUMENTS.install_infra_path,
                                                     "ibm-spectrum-scale-install-infra",
                                                     cluster_type))
        print('[scale_nodes]')
        print(node_template)
        print('[all:vars]')
        for each_key in config['all:vars']:
            print("%s: %s" % (each_key, config.get('all:vars', each_key)))

    # Step-6: Create group_vars directory
    create_directory("%s/%s/%s" % (ARGUMENTS.install_infra_path,
                                   "ibm-spectrum-scale-install-infra",
                                   "group_vars"))
    # Step-7: Create group_vars
    with open("%s/%s/%s/%s" % (ARGUMENTS.install_infra_path,
                               "ibm-spectrum-scale-install-infra",
                               "group_vars",
                               "%s_cluster_config.yaml" % cluster_type), 'w') as groupvar:
        yaml.dump(scale_config, groupvar, default_flow_style=False)
    if ARGUMENTS.verbose:
        print("group_vars content:\n%s" % yaml.dump(
            scale_config, default_flow_style=False))

    if cluster_type in ['storage', 'combined']:
        disks_list = get_disks_list(len(TF['vpc_availability_zones']),
                                    TF['storage_cluster_with_data_volume_mapping'],
                                    TF['storage_cluster_desc_data_volume_mapping'])
        scale_storage = initialize_scale_storage_details(len(TF['vpc_availability_zones']),
                                                         TF['storage_cluster_filesystem_mountpoint'],
                                                         TF['filesystem_block_size'],
                                                         disks_list)
        with open("%s/%s/%s/%s" % (ARGUMENTS.install_infra_path,
                                   "ibm-spectrum-scale-install-infra",
                                   "group_vars",
                                   "%s_cluster_config.yaml" % cluster_type), 'a') as groupvar:
            yaml.dump(scale_storage, groupvar, default_flow_style=False)
        if ARGUMENTS.verbose:
            print("group_vars content:\n%s" % yaml.dump(
                scale_storage, default_flow_style=False))
