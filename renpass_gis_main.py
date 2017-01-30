# -*- coding: utf-8 -*-
""" renpass_gis

Usage:
  renpass_gis_main.py [options] NODE_DATA SEQ_DATA
  renpass_gis_main.py -h | --help | --version

Examples:

  renpass_gis_main.py -o gurobi path/to/scenario.csv path/to/scenario-seq.csv

Arguments:

  NODE_DATA                  CSV-file containing data for nodes and flows.
  SEQ_DATA                   CSV-file with data for sequences.

Options:

  -h --help                  Show this screen and exit.
  -o --solver=SOLVER         Solver to be used. [default: cbc]
     --output-directory=DIR  Directory to write results to. [default: results]
     --date-from=TIMESTAMP   Start interval of simulation. --date-from
                             and --date-to create a DatetimeIndex, which length
                             should always reflect the number of rows in SEQ_DATA.
                             It cannot be used to select / slice the data.
                             [default: 2014-01-01 00:00:00]
     --date-to=TIMESTAMP     End interval. [default: 2014-12-31 23:00:00]
     --version               Show version.
"""

import os
import logging
import pandas as pd

from datetime import datetime
from oemof.tools import logger
from oemof.solph import OperationalModel, EnergySystem, GROUPINGS
from oemof.solph import NodesFromCSV
from oemof.outputlib import ResultsDataFrame
from docopt import docopt


###############################################################################

def stopwatch():
    if not hasattr(stopwatch, 'now'):
        stopwatch.now = datetime.now()
        return None
    last = stopwatch.now
    stopwatch.now = datetime.now()
    return str(stopwatch.now-last)[0:-4]


def create_nodes(**arguments):
    """Creates nodes with their respective sequences

    Parameters
    ----------
    **arguments : key word arguments
        Arguments passed from command line
    """
    nodes = NodesFromCSV(file_nodes_flows=arguments['NODE_DATA'],
                         file_nodes_flows_sequences=arguments['SEQ_DATA'],
                         delimiter=',')

    return nodes


def create_energysystem(nodes, **arguments):
    """Creates the energysystem.

    Parameters
    ----------
    nodes:
        A list of entities that comprise the energy system
    **arguments : key word arguments
        Arguments passed from command line
    """

    datetime_index = pd.date_range(arguments['--date-from'],
                                   arguments['--date-to'],
                                   freq='60min')

    es = EnergySystem(entities=nodes,
                      groupings=GROUPINGS,
                      timeindex=datetime_index)

    return es


def simulate(es=None, **arguments):
    """Creates the optimization model, solves it and writes back results to
    energy system object

    Parameters
    ----------
    es : :class:`oemof.solph.network.EnergySystem` object
        Energy system holding nodes, grouping functions and other important
        information.
    **arguments : key word arguments
        Arguments passed from command line
    """

    om = OperationalModel(es)

    logging.info('OM creation time: ' + stopwatch())

    om.receive_duals()

    om.solve(solver=arguments['--solver'], solve_kwargs={'tee': True})

    logging.info('Optimization time: ' + stopwatch())

    return om


def write_results(es, om, **arguments):
    """Write results to CSV-files

    Parameters
    ----------
    es : :class:`oemof.solph.network.EnergySystem` object
        Energy system holding nodes, grouping functions and other important
        information.
    om : :class:'oemof.solph.models.OperationalModel' object for operational
        simulation with optimized dispatch
    **arguments : key word arguments
        Arguments passed from command line

    """
    # output: create pandas dataframe with results

    results = ResultsDataFrame(energy_system=es)

    # postprocessing: write complete result dataframe to file system

    if not os.path.isdir(arguments['--output-directory']):
        os.mkdir(arguments['--output-directory'])

    results_path = arguments['--output-directory']

    date = str(datetime.now())

    file_name = 'scenario_' + os.path.basename(arguments['NODE_DATA'])\
        .replace('.csv', '_') + date + '_' + 'results_complete.csv'

    results.to_csv(os.path.join(results_path, file_name))

    # postprocessing: write dispatch and prices for all regions to file system

    # country codes
    country_codes = ['AT', 'BE', 'CH', 'CZ', 'DE', 'DK', 'FR', 'LU', 'NL',
                     'NO', 'PL', 'SE']

    for cc in country_codes:
        # build single dataframe for electric buses
        inputs = results.slice_unstacked(bus_label=cc + '_bus_el',
                                         type='to_bus',
                                         date_from=arguments['--date-from'],
                                         date_to=arguments['--date-to'],
                                         formatted=True)

        outputs = results.slice_unstacked(bus_label=(cc + '_bus_el'),
                                          type='from_bus',
                                          date_from=arguments['--date-from'],
                                          date_to=arguments['--date-to'],
                                          formatted=True)

        other = results.slice_unstacked(bus_label=cc + '_bus_el',
                                        type='other',
                                        date_from=arguments['--date-from'],
                                        date_to=arguments['--date-to'],
                                        formatted=True)

        # AT, DE and LU are treated as one bidding area
        if cc == 'DE':
            for c in ['DE', 'AT', 'LU']:
                # rename redundant columns
                inputs.rename(columns={c + '_storage_phs':
                                       c + '_storage_phs_out'},
                              inplace=True)
                outputs.rename(columns={c + '_storage_phs':
                                        c + '_storage_phs_in'},
                               inplace=True)
                other.rename(columns={c + '_storage_phs':
                                      c + '_storage_phs_level'},
                             inplace=True)

                # data from model in MWh
                country_data = pd.concat([inputs, outputs, other], axis=1)
        else:
            # rename redundant columns
            inputs.rename(columns={cc + '_storage_phs': cc +
                                   '_storage_phs_out'},
                          inplace=True)
            outputs.rename(columns={cc + '_storage_phs': cc +
                                    '_storage_phs_in'},
                           inplace=True)
            other.rename(columns={cc + '_storage_phs': cc +
                                  '_storage_phs_level'},
                         inplace=True)

            # data from model in MWh
            country_data = pd.concat([inputs, outputs, other], axis=1)

        # sort columns and save as csv file
        file_name = 'scenario_' + os.path.basename(arguments['NODE_DATA'])\
            .replace('.csv', '_') + date + '_' + cc + '.csv'
        country_data.sort_index(axis=1, inplace=True)
        country_data.to_csv(os.path.join(results_path, file_name))

    return


def main(**arguments):
    """
    """
    logging.info('Starting renpass_gis!')

    stopwatch()

    # create nodes from csv
    nodes = create_nodes(**arguments)

    # create energy system and pass nodes
    es = create_energysystem(nodes.values(), **arguments)

    # create optimization model and solve it
    om = simulate(es=es, **arguments)

    # write results in output directory
    write_results(es=es, om=om, **arguments)
    logging.info('Done! \n Check the results')

    return


###############################################################################

if __name__ == '__main__':
    arguments = docopt(__doc__, version='renpass_gis v0.1')
    logger.define_logging()
    main(**arguments)
