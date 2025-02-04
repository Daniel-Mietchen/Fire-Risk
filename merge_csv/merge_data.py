# !/bin/python3

import pandas as pd
import json
import logging
import sys
from sqlalchemy import create_engine
import math

USAGE = """
Merge CSVs for fire-risk data

USAGE: 
	python3 merge_data.py [CSV_1_Name or --help] [CSV_1_Path] [CSV_2_Name] [CSV_2_Path] ...
"""

##########################
## Original Data Config ##
##########################
PARCEL_AREA_DETAILS = "parcel_area"
REAL_ESTATE_COMMERCIAL_DETAILS = "real_estate_commercial"
REAL_ESTATE_RESIDENTIAL_DETAILS = "real_estate_residential"
REAL_ESTATE_BASE = "real_estate_base"

########################
## Merged Data Config ##
########################
INDEX = "parcelnumber"
SHARED_ATTRIBUTES = ["usecode", "yearbuilt"]

#####################
## postgres config ##
#####################
POSTGRES_ENDPOINT = "postgres://postgres:mysecretpassword@127.0.0.1:5431/firerisk"


def _combineSharedAttributes(df):
    """
    combine shared attributes to make more cleaner columns
    """

    for s in SHARED_ATTRIBUTES:
        newValues = []

        for index, row in df.iterrows():

            useResidential = False

            if s == "yearbuilt":
                useResidential = math.isnan(
                    row[REAL_ESTATE_RESIDENTIAL_DETAILS + "-" + s])
            if s == "usecode":
                useResidential = row[REAL_ESTATE_RESIDENTIAL_DETAILS + "-" +
                                     s] == ""

            if useResidential:
                newValues.append(row[REAL_ESTATE_COMMERCIAL_DETAILS + "-" + s])
            else:
                newValues.append(row[REAL_ESTATE_RESIDENTIAL_DETAILS + "-" +
                                     s])

        df = df.drop(columns=[
            REAL_ESTATE_COMMERCIAL_DETAILS + "-" +
            s, REAL_ESTATE_RESIDENTIAL_DETAILS + "-" + s
        ])
        df.insert(0, s, newValues, True)
    return df


def _normalizeCol(csvName, col):
    """
    returns shared attribute name is it is one
    """
    col = col.lower()
    if col == INDEX: return col
    # add suffix if not standardized
    return "{}-{}".format(csvName, col)


def _fieldIsWanted(csvName, col):
    """
    determines if field is wanted based on the csv name
    """
    col = col.lower()
    if csvName == PARCEL_AREA_DETAILS:
        return col in [
            "objectid", "assessment", "geoparcelidentificationnumber",
            "legaldescription", "lotsquarefeet", "parcelnumber", "zoning",
            "esr_oid"
        ]

    if csvName == REAL_ESTATE_COMMERCIAL_DETAILS:
        return col in [
            "recordid_int",
            "parcelnumber",
            "usecode",
            "yearbuilt",
            "grossarea",
            "storyheight",
            "numberofstories",
        ]

    if csvName == REAL_ESTATE_RESIDENTIAL_DETAILS:
        return col in [
            "recordid_int",
            "parcelnumber",
            "usecode",
            "style",
            "grade",
            "roof",
            "flooring",
            "heating",
            "fireplace",
            "yearbuilt",
            "totalrooms",
            "bedrooms",
            "halfbathrooms",
            "fullbathrooms",
            "basementgarage",
            "basement",
            "finishedbasement",
            "basementtype",
            "externalwalls",
            "numberofstories",
            "squarefootagefinishedliving",
        ]

    if csvName == REAL_ESTATE_BASE:
        return col in [
            "recordid_int",
            "parcelnumber",
            "streetnumber",
            "streetname",
            "unit",
            "statecode",
            "zone",
            "acerage",
        ]

    return False


def _mergeInData(csv, name, mergedCsv):
    """
    merges in data from csv into mergedCsv, passed by reference
    """
    logging.info("Reading in csv: %s", csv)
    df = pd.read_csv(csv)
    # first clean up columns in df
    for col in df.columns:
        # dont add if field isn't needed
        if _fieldIsWanted(name, col):
            # normalize to sharedAttributes, if needed
            df = df.rename(columns={col: _normalizeCol(name, col)})
        else:
            df = df.drop(columns=[col])

    logging.debug("updated columns in {}: {}".format(name, df.columns))

    # return this chart if there's nothing in the current chart
    if len(mergedCsv.index) == 0:
        return df
    # else return merged CSV on index
    merged = mergedCsv.join(df.set_index(INDEX), on=INDEX)
    # drop duplicates, if any
    merged.drop_duplicates(subset=[INDEX], inplace=True)
    return merged


def _insertIntoPostgres(df):
    """
    inserts data into postgres
    """
    table = "parcels"
    engine = create_engine(POSTGRES_ENDPOINT)
    logging.debug("dropping previous table")
    engine.execute('drop table if exists {}'.format(table))
    logging.debug("inserting new data")
    df.to_sql(table, engine)


#    logging.debug("inserted data into db: {}".format(
#        engine.execute('SELECT * FROM {}'.format(table)).fetchall()))

if __name__ == '__main__':
    # parse args
    if len(sys.argv) < 2 or sys.argv[1] == "--help":
        print(USAGE)
        sys.exit(1)
    # init data file
    logging.basicConfig(filename="merge_data.log", level=logging.DEBUG)

    # start merge
    mergedCsv = pd.DataFrame()
    for i in range(1, len(sys.argv), 2):
        csv = sys.argv[i + 1]
        name = sys.argv[i]
        mergedCsv = _mergeInData(csv, name, mergedCsv)
        logging.debug("merged in chart {}:\n{}".format(name, mergedCsv))
    mergedCsv = _combineSharedAttributes(mergedCsv)
    # output csv to file
    mergedCsv.to_csv("merged.csv", index=INDEX)
    # insert into postgres
    _insertIntoPostgres(mergedCsv)
